"""Source pinning, structural detection and exact snapshots in Blender."""

import hashlib, json, math, struct
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, object_name=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    elif path.suffix.lower() == ".glb":
        bpy.ops.import_scene.gltf(filepath=str(path), disable_bone_shape=True)
    else:
        raise ValueError("Use a native humanoid Blender source or GLB")
    scene = bpy.context.scene
    if scene is None:
        scene = bpy.data.scenes.new("Humanoid source")
        for window in bpy.context.window_manager.windows:
            window.scene = scene
    meshes = [
        o
        for o in scene.objects
        if o.type == "MESH" and (object_name is None or o.name == object_name)
    ]
    if not meshes:
        meshes = [
            o
            for o in bpy.data.objects
            if o.type == "MESH" and (object_name is None or o.name == object_name)
        ]
    if len(meshes) != 1:
        raise ValueError("Select one source mesh explicitly")
    mesh = meshes[0]
    modifiers = [m for m in mesh.modifiers if m.show_viewport or m.show_render]
    if (
        len(modifiers) != 1
        or modifiers[0].type != "ARMATURE"
        or modifiers[0].object is None
    ):
        return mesh, None
    rig = modifiers[0].object
    objects = {mesh, rig}
    for obj in tuple(objects):
        parent = obj.parent
        while parent:
            objects.add(parent)
            parent = parent.parent
    for obj in objects:
        if obj.name not in scene.objects:
            scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    return mesh, rig


def snapshot(mesh, rig):
    return dict(
        vertices=[list(v.co) for v in mesh.data.vertices],
        polygons=[list(p.vertices) for p in mesh.data.polygons],
        uv=(
            [list(v.uv) for v in mesh.data.uv_layers.active.data]
            if mesh.data.uv_layers.active
            else None
        ),
        mesh_matrix=[list(r) for r in mesh.matrix_world],
        rig_matrix=[list(r) for r in rig.matrix_world],
        bones={
            b.name: dict(
                parent=b.parent.name if b.parent else None,
                matrix=[list(r) for r in b.matrix_local],
            )
            for b in rig.data.bones
        },
    )


def weights(mesh):
    names = {g.index: g.name for g in mesh.vertex_groups}
    return [
        {names[g.group]: float(g.weight) for g in v.groups if g.weight > 0}
        for v in mesh.data.vertices
    ]


def apply_weights(mesh, rows):
    names = [g.name for g in mesh.vertex_groups]
    mesh.vertex_groups.clear()
    groups = {n: mesh.vertex_groups.new(name=n) for n in names}
    for index, row in enumerate(rows):
        for name, value in row.items():
            groups[name].add((index,), value, "REPLACE")


def detect(mesh, rig, parents):
    if rig is None:
        return dict(applicable=False, reason="No single native armature binding")
    if {b.name: b.parent.name if b.parent else None for b in rig.data.bones} != parents:
        return dict(
            applicable=False, reason="Not the native eighteen-joint humanoid hierarchy"
        )
    if len(mesh.data.vertices) > 200000 or len(mesh.data.polygons) > 400000:
        return dict(
            applicable=False,
            requires_attention=True,
            reason="Source exceeds the bounded humanoid profile",
        )
    if min(mesh.matrix_world.determinant(), rig.matrix_world.determinant()) <= 1e-10:
        return dict(
            applicable=False,
            requires_attention=True,
            reason="Singular or mirrored native source frame",
        )
    residual = max(
        abs(v - x)
        for b in rig.pose.bones
        for row, identity in zip(b.matrix_basis, Matrix.Identity(4))
        for v, x in zip(row, identity)
    )
    if (
        mesh.data.shape_keys
        or rig.constraints
        or any(b.constraints for b in rig.pose.bones)
        or any(
            o.animation_data
            and (
                o.animation_data.action
                or o.animation_data.drivers
                or o.animation_data.nla_tracks
            )
            for o in (mesh, rig, mesh.data, rig.data)
        )
        or residual > 2e-5
    ):
        return dict(
            applicable=False,
            reason="Use a static source in its native rest pose; no animation migration",
        )
    rows = weights(mesh)
    support = {
        n: sum(sum(v for k, v in row.items() if k == n) > 0.5 for row in rows)
        for n in (
            "head",
            "upper_arm.L",
            "upper_arm.R",
            "forearm.L",
            "forearm.R",
            "thigh.L",
            "thigh.R",
            "shin.L",
            "shin.R",
        )
    }
    applicable = (
        len(rows) >= 100
        and min(support.values()) >= 4
        and all(set(row) <= set(parents) - {"root"} for row in rows)
    )
    return dict(
        applicable=applicable,
        profile="native-humanoid-deformation-v1",
        authority="native hierarchy plus bilateral weighted limb/head support; not anatomical recognition",
        rest_basis_residual=residual,
        rest_basis_tolerance=2e-5,
        support=support,
    )


def glb_frames(path):
    data = Path(path).read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20 : 20 + length])
    nodes = g["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    world = {}

    def matrix(index):
        if index not in world:
            n = nodes[index]
            if "matrix" in n:
                m = Matrix([n["matrix"][i::4] for i in range(4)])
            else:
                q = n.get("rotation", [0, 0, 0, 1])
                m = (
                    Matrix.Translation(n.get("translation", [0, 0, 0]))
                    @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4()
                    @ Matrix.Diagonal((*n.get("scale", [1, 1, 1]), 1))
                )
            world[index] = matrix(parent[index]) @ m if index in parent else m
        return world[index]

    return {
        nodes[i]["name"]: [list(row) for row in matrix(i)]
        for skin in g.get("skins", [])
        for i in skin["joints"]
    }


def frame_error(a, b):
    if a.keys() != b.keys():
        raise ValueError("Native joint names changed on export")
    return max(
        abs(x - y)
        for name in a
        for ra, rb in zip(a[name], b[name])
        for x, y in zip(ra, rb)
    )


def appearance_signature(path):
    raw = Path(path).read_bytes()
    size = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20 : 20 + size])
    offset = 20 + size
    binary = raw[offset + 8 :]
    hashes = []
    for image in g.get("images", []):
        if "bufferView" not in image:
            raise ValueError("Require self-contained GLB image buffers")
        view = g["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        hashes.append(
            hashlib.sha256(binary[start : start + view["byteLength"]]).hexdigest()
        )
    materials = json.dumps(g.get("materials", []), sort_keys=True, allow_nan=False)
    return dict(
        image_sha256=sorted(hashes),
        materials_sha256=hashlib.sha256(materials.encode()).hexdigest(),
    )
