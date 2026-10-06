"""Fail-before-publish modular checks against the unmodified source surface."""

from __future__ import annotations

import math
from types import SimpleNamespace

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from ..canonical_motion.source import cleanup_imported_data, snapshot_blender_data
from .fidelity import _surface_error, _tree, _weight_error
from .fidelity_samples import material_signatures, sample_state
from .modular_gltf import read_accessor, read_glb
from .modular_partition import REGION_ID_KEY, REGION_ROLE_KEY, SEAM_POLICY, SEAM_POLICY_KEY


_AXES = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
POSITION_TOLERANCE = 2.0e-4
ATTRIBUTE_TOLERANCE = 2.0e-4
IMPORTED_NORMAL_TOLERANCE = 5.0e-4
RAW_NORMAL_TOLERANCE = 2.0e-6
COLOR_TOLERANCE = 4.0e-3
WEIGHT_TOLERANCE = 1.0e-4


def _members(plan, spec):
    ids = {region.id for region in spec.regions}
    partitioned = {obj.get(REGION_ID_KEY): obj for obj in plan.mesh_objects}
    if set(partitioned) == ids and len(partitioned) == len(plan.mesh_objects):
        return {key: (obj, tuple(range(len(obj.data.polygons))))
                for key, obj in partitioned.items()}
    result = {}
    for obj in plan.mesh_objects:
        owners = spec.ownership.get(obj.name)
        if owners is None or len(owners) != len(obj.data.polygons):
            raise ValueError("Modular expectation requires complete source face ownership.")
        for key in ids:
            faces = tuple(index for index, owner in enumerate(owners) if owner == key)
            if faces:
                if key in result:
                    raise ValueError("A modular V1 region spans multiple source frames.")
                result[key] = (obj, faces)
    if set(result) != ids:
        raise ValueError("Modular expectation lost a declared region.")
    return result


def _corner_records(obj, faces):
    data = obj.data
    data.calc_loop_triangles()
    normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
    material_cache = {}
    result = []
    for triangle in data.loop_triangles:
        if triangle.polygon_index not in faces:
            continue
        polygon = data.polygons[triangle.polygon_index]
        material = data.materials[polygon.material_index] if polygon.material_index < len(data.materials) else None
        pointer = material.as_pointer() if material else 0
        if pointer not in material_cache:
            holder = SimpleNamespace(data=SimpleNamespace(materials=(material,)))
            material_cache[pointer] = next(iter(material_signatures((holder,))), None)
        for loop in triangle.loops:
            vertex = data.loops[loop].vertex_index
            colors = tuple(tuple(layer.data[loop if layer.domain == "CORNER" else vertex].color)
                           for layer in data.color_attributes)
            result.append((tuple(obj.matrix_world @ data.vertices[vertex].co),
                           tuple((normal_matrix @ data.corner_normals[loop].vector).normalized()),
                           tuple(tuple(layer.data[loop].uv) for layer in data.uv_layers),
                           colors, material_cache[pointer]))
    if not result:
        raise ValueError("Modular region has no triangle corners.")
    return tuple(result)


def _region_samples(members, armature):
    result = {}
    bones = set(armature.data.bones.keys())
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for key, (obj, faces) in members.items():
        used = sorted({index for face in faces for index in obj.data.polygons[face].vertices})
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            if len(mesh.vertices) != len(obj.data.vertices):
                raise ValueError("Modular fidelity rejects topology-changing deformation.")
            groups = {group.index: group.name for group in obj.vertex_groups
                      if group.name in bones}
            points, skin = [], []
            for index in used:
                point = tuple(evaluated.matrix_world @ mesh.vertices[index].co)
                points.append(point)
                weights = {groups[item.group]: float(item.weight)
                           for item in obj.data.vertices[index].groups
                           if item.group in groups and item.weight > 1.0e-7}
                total = sum(weights.values())
                if not total:
                    raise ValueError(f"Modular region {key!r} has an unbound vertex.")
                skin.append((point, {name: value / total for name, value in weights.items()}))
            result[key] = {"points": tuple(points), "skin": tuple(skin)}
        finally:
            evaluated.to_mesh_clear()
    return result


def _reset(ids, armature):
    for item in ids:
        if item.animation_data:
            item.animation_data.action = None
            item.animation_data.use_nla = False
    for bone in armature.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()


def _flatten(matrix):
    return tuple(float(value) for row in matrix for value in row)


def capture_modular_expectation(plan, spec):
    """Capture source face attributes, bind pose and one multi-joint stress pose."""
    armature = plan.armature_object
    if armature is None:
        raise ValueError("Modular fidelity requires the common rig.")
    members = _members(plan, spec)
    with sample_state(plan.mesh_objects, armature, plan.auxiliary_objects) as ids:
        _reset(ids, armature)
        armature.data.pose_position = "REST"
        bpy.context.view_layer.update()
        corners = {key: _corner_records(obj, set(faces)) for key, (obj, faces) in members.items()}
        rest = _region_samples(members, armature)
        joint_rest = {bone.name: _flatten(armature.matrix_world @ bone.matrix_local)
                      for bone in armature.data.bones}
        hierarchy = {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}
        armature.data.pose_position = "POSE"
        # All joints move, including the axial chain. Non-collinear rotations
        # exercise blended skinning; each region remains on the same common rig.
        for index, bone in enumerate(armature.pose.bones):
            bone.matrix_basis = Euler((0.08 + 0.03 * (index % 3),
                                       -0.11 + 0.02 * (index % 5),
                                       0.09 * (-1 if index % 2 else 1)), "XYZ").to_matrix().to_4x4()
        bpy.context.view_layer.update()
        compound = _region_samples(members, armature)
        joint_pose = {bone.name: _flatten(armature.matrix_world @ bone.matrix)
                      for bone in armature.pose.bones}
    return {"corners": corners, "rest": rest, "compound": compound,
            "joint_rest": joint_rest, "joint_pose": joint_pose, "hierarchy": hierarchy,
            "spec": spec.to_dict()}


def _matrix(values):
    return Matrix(tuple(tuple(values[row * 4 + column] for column in range(4)) for row in range(4)))


def _matrix_error(left, right):
    return max(abs(left[row][column] - right[row][column]) for row in range(4) for column in range(4))


def _node_matrix(node):
    if "matrix" in node:
        values = node["matrix"]
        if len(values) != 16 or any(not math.isfinite(value) for value in values):
            raise ValueError("Invalid modular node matrix.")
        return Matrix(tuple(tuple(values[column * 4 + row] for column in range(4)) for row in range(4)))
    translation, rotation, scale = node.get("translation", (0, 0, 0)), node.get("rotation", (0, 0, 0, 1)), node.get("scale", (1, 1, 1))
    if len(translation) != 3 or len(rotation) != 4 or len(scale) != 3 or any(
            not math.isfinite(value) for value in (*translation, *rotation, *scale)):
        raise ValueError("Invalid modular node TRS.")
    return Matrix.LocRotScale(Vector(translation), Quaternion((rotation[3], *rotation[:3])), Vector(scale))


def _raw_bindings(path, spec, expected):
    document, binary = read_glb(path)
    envelope = document.get("asset", {}).get("extras", {}).get("meshvenn_modular_character")
    if not isinstance(envelope, dict) or envelope.get("spec") != expected["spec"]:
        raise ValueError("GLB modular authoring metadata differs from the source contract.")
    bindings = envelope.get("bindings", {})
    nodes = document.get("nodes", [])
    region_nodes = bindings.get("region_nodes", {})
    if set(region_nodes) != {region.id for region in spec.regions}:
        raise ValueError("GLB modular region inventory differs from the source contract.")
    parents = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            if child in parents or not isinstance(child, int) or not 0 <= child < len(nodes):
                raise ValueError("Invalid or multiply-parented modular node.")
            parents[child] = index
    global_matrices = {}
    def world(index, active=()):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(nodes) or index in active:
            raise ValueError("Invalid or cyclic modular node binding.")
        if index not in global_matrices:
            local = _node_matrix(nodes[index])
            global_matrices[index] = world(parents[index], (*active, index)) @ local if index in parents else local
        return global_matrices[index]
    skin_index = bindings.get("skin")
    skins = document.get("skins", [])
    if isinstance(skin_index, bool) or not isinstance(skin_index, int) or not 0 <= skin_index < len(skins) or len(skins) != 1:
        raise ValueError("Modular GLB must contain one shared skin.")
    skin = skins[skin_index]
    joints = skin.get("joints", [])
    joint_nodes = bindings.get("joint_nodes", {})
    if (set(joint_nodes) != set(expected["joint_rest"]) or len(joints) != len(joint_nodes)
            or len(set(joints)) != len(joints) or set(joints) != set(joint_nodes.values())):
        raise ValueError("Modular GLB changed the common joint inventory.")
    matrices = read_accessor(document, binary, skin.get("inverseBindMatrices"))
    if len(matrices) != len(joints) or any(len(matrix) != 16 for matrix in matrices):
        raise ValueError("Modular GLB inverse-bind matrix count differs from its joints.")
    by_node = dict(zip(joints, matrices))
    bind_error = joint_error = socket_error = 0.0
    for name, index in joint_nodes.items():
        if nodes[index].get("name") != name:
            raise ValueError("Modular joint binding renamed a native bone.")
        source_rest = _AXES @ _matrix(expected["joint_rest"][name])
        joint_error = max(joint_error, _matrix_error(world(index), source_rest))
        inverse = Matrix(tuple(tuple(by_node[index][column * 4 + row] for column in range(4)) for row in range(4)))
        bind_error = max(bind_error, _matrix_error(inverse, source_rest.inverted()))
        expected_parent = expected["hierarchy"][name]
        if expected_parent is not None and parents.get(index) != joint_nodes[expected_parent]:
            raise ValueError("Modular GLB changed native bone parentage.")
    raw_normal_error = 0.0
    raw_corner_metrics = {}
    source_points = [record[0] for records in expected["corners"].values() for record in records]
    raw_extent = max(max(point[axis] for point in source_points) - min(point[axis] for point in source_points) for axis in range(3))
    raw_tolerance = max(raw_extent, 1.0e-6) * POSITION_TOLERANCE
    for region in spec.regions:
        index = region_nodes[region.id]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(nodes):
            raise ValueError("Modular region references an invalid node.")
        node = nodes[index]
        if node.get("skin") != skin_index or "mesh" not in node or node.get("name") != region.node_name:
            raise ValueError("Modular region lost its stable mesh name or common skin binding.")
        if node.get("extras", {}).get(REGION_ID_KEY) != region.id:
            raise ValueError("Modular region lost its stable exported ID.")
        mesh_index = node["mesh"]
        mesh_entries = document.get("meshes", [])
        if type(mesh_index) is not int or not 0 <= mesh_index < len(mesh_entries):
            raise ValueError("Modular region has an invalid mesh reference.")
        primitives = mesh_entries[mesh_index].get("primitives", [])
        if not primitives:
            raise ValueError("Modular region has no exported primitives.")
        raw_corners = []
        for primitive in primitives:
            attributes = primitive.get("attributes", {})
            if "JOINTS_1" in attributes or "WEIGHTS_1" in attributes:
                raise ValueError("Modular V1 cannot export more than four skin influences.")
            weights = read_accessor(document, binary, attributes.get("WEIGHTS_0"))
            influences = read_accessor(document, binary, attributes.get("JOINTS_0"))
            positions = read_accessor(document, binary, attributes.get("POSITION"))
            normals = read_accessor(document, binary, attributes.get("NORMAL"))
            normal_accessor = document["accessors"][attributes["NORMAL"]]
            if normal_accessor.get("componentType") != 5126 or normal_accessor.get("type") != "VEC3":
                raise ValueError("Modular GLB normals must be unquantized float32 VEC3.")
            if len(weights) != len(influences) or len(weights) != len(positions):
                raise ValueError("Modular GLB skin accessors differ from their vertex count.")
            for values, indices in zip(weights, influences):
                if len(values) != 4 or len(indices) != 4 or any(
                        type(index) is not int or not 0 <= index < len(joints) for index in indices):
                    raise ValueError("Modular GLB has invalid four-component native joint influences.")
                active = [index for weight, index in zip(values, indices) if weight > 1.0e-7]
                if (any(weight < 0 for weight in values) or not 1 <= len(active) <= 4
                        or len(set(active)) != len(active) or abs(sum(values) - 1) > WEIGHT_TOLERANCE):
                    raise ValueError("Modular GLB contains unnormalized, negative or duplicate skin influences.")
            if len(normals) != len(positions) or primitive.get("mode", 4) != 4:
                raise ValueError("Modular GLB must preserve triangle position/normal alignment.")
            texcoords = [read_accessor(document, binary, attributes[name]) for name in sorted(
                (name for name in attributes if name.startswith("TEXCOORD_")), key=lambda name: int(name.split("_")[-1]))]
            if any(len(layer) != len(positions) for layer in texcoords):
                raise ValueError("Modular GLB UV accessor differs from its vertex count.")
            indices = (tuple(row[0] for row in read_accessor(document, binary, primitive["indices"]))
                       if "indices" in primitive else tuple(range(len(positions))))
            if len(indices) % 3 or any(type(vertex) is not int or not 0 <= vertex < len(positions) for vertex in indices):
                raise ValueError("Modular GLB triangle indices are invalid.")
            normal_matrix = world(index).to_3x3().inverted().transposed()
            for vertex in indices:
                normal = Vector(normals[vertex])
                if abs(normal.length_squared - 1) > 2e-6:
                    raise ValueError("Modular GLB has non-unit raw vertex normals.")
                point = _AXES.inverted() @ world(index) @ Vector(positions[vertex])
                normal = _AXES.to_3x3().inverted() @ (normal_matrix @ normal).normalized()
                raw_corners.append((tuple(point), tuple(normal),
                                    tuple((uv[vertex][0], 1 - uv[vertex][1]) for uv in texcoords), (), None))
        raw_normal_error = max(raw_normal_error, _corner_error(expected["corners"][region.id], tuple(raw_corners),
                                                              raw_tolerance, normal_tolerance=RAW_NORMAL_TOLERANCE,
                                                              ignore_color_material=True, report=raw_corner_metrics))
    socket_bindings = bindings.get("sockets", {})
    if set(socket_bindings) != {socket.id for socket in spec.sockets}:
        raise ValueError("Modular GLB changed the socket inventory.")
    for socket in spec.sockets:
        binding = socket_bindings[socket.id]
        joint = joint_nodes[socket.parent_bone]
        if binding != {"parent_joint_node": joint, "owner_region_node": region_nodes[socket.region_id]}:
            raise ValueError("Modular socket lost its joint or region binding.")
        rotation = socket.rotation
        local = Matrix.LocRotScale(Vector(socket.translation), Quaternion((rotation[3], *rotation[:3])), Vector(socket.scale))
        rest = _AXES @ _matrix(expected["joint_rest"][socket.parent_bone])
        socket_error = max(socket_error, _matrix_error(world(joint) @ local, rest @ local))
    if max(bind_error, joint_error, socket_error) > ATTRIBUTE_TOLERANCE:
        raise ValueError(f"Modular GLB changed bind/rest/socket matrices: {bind_error:.6g}/{joint_error:.6g}/{socket_error:.6g}.")
    return {"max_inverse_bind_error": bind_error, "max_joint_rest_error": joint_error,
            "max_socket_rest_error": socket_error, "skin_count": len(skins),
            "raw_normalized_four_influence_skin_verified": True,
            "max_raw_corner_normal_uv_error": raw_normal_error, "raw_normal_tolerance": RAW_NORMAL_TOLERANCE,
            "max_raw_normal_error": raw_corner_metrics.get("max_normal_error", 0.0),
            "max_raw_uv_error": raw_corner_metrics.get("max_uv_error", 0.0),
            "raw_triangle_count": raw_corner_metrics.get("matched_triangle_count", 0),
            "_joint_rest_matrices": {name: _flatten(world(index)) for name, index in joint_nodes.items()}}


def _corner_error(left, right, tolerance, *, normal_tolerance=IMPORTED_NORMAL_TOLERANCE,
                  ignore_color_material=False, report=None):
    if len(left) != len(right) or len(left) % 3:
        raise ValueError("Modular GLB changed the number of triangle corners.")
    source = tuple(left[index:index + 3] for index in range(0, len(left), 3))
    target = tuple(right[index:index + 3] for index in range(0, len(right), 3))
    def center(triangle):
        return tuple(sum(record[0][axis] for record in triangle) / 3 for axis in range(3))
    tree = _tree(tuple(center(triangle) for triangle in target))
    consumed, maximum = set(), 0.0
    for triangle in source:
        matches, diagnostics = [], []
        for _, index, _ in tree.find_range(center(triangle), tolerance):
            if index in consumed:
                continue
            other_triangle = target[index]
            # Cyclic corner order is equivalent; reversed winding is not.
            for shift in range(3):
                score, valid = 0.0, True
                normal_max = uv_max = color_max = 0.0
                for corner, record in enumerate(triangle):
                    other = other_triangle[(corner + shift) % 3]
                    if (Vector(record[0]) - Vector(other[0])).length > tolerance:
                        valid = False
                        break
                    if (len(record[2]) != len(other[2]) or (not ignore_color_material and
                            (record[4] != other[4] or len(record[3]) != len(other[3])))):
                        diagnostics.append(f"material_match={record[4] == other[4]}, UVs={len(record[2])}/{len(other[2])}, colors={len(record[3])}/{len(other[3])}")
                        valid = False
                        break
                    normal_error = max(abs(a - b) for a, b in zip(record[1], other[1]))
                    uv_error = max((abs(a - b) for a, b in zip(
                        (v for uv in record[2] for v in uv), (v for uv in other[2] for v in uv))), default=0.0)
                    color = 0.0 if ignore_color_material else max((abs(a - b) for a, b in zip(
                        (v for rgba in record[3] for v in rgba),
                        (v for rgba in other[3] for v in rgba))), default=0.0)
                    if normal_error > normal_tolerance or uv_error > ATTRIBUTE_TOLERANCE or color > COLOR_TOLERANCE:
                        diagnostics.append(f"normal={normal_error:.6g}, UV={uv_error:.6g}, color={color:.6g}")
                        valid = False
                        break
                    score = max(score, normal_error, uv_error, color)
                    normal_max, uv_max, color_max = max(normal_max, normal_error), max(uv_max, uv_error), max(color_max, color)
                if valid:
                    matches.append((score, index, normal_max, uv_max, color_max))
        if not matches:
            raise ValueError("Modular GLB changed triangle coverage/winding or a corner normal, UV, color or material assignment: "
                             f"center={center(triangle)}, candidates={diagnostics[:6]}.")
        score, index, normal_max, uv_max, color_max = min(matches)
        consumed.add(index)
        maximum = max(maximum, score)
        if report is not None:
            report["max_normal_error"] = max(report.get("max_normal_error", 0.0), normal_max)
            report["max_uv_error"] = max(report.get("max_uv_error", 0.0), uv_max)
            report["max_color_error"] = max(report.get("max_color_error", 0.0), color_max)
            report["matched_triangle_count"] = report.get("matched_triangle_count", 0) + 1
    if len(consumed) != len(target):
        raise ValueError("Modular GLB triangle coverage is not bijective.")
    return maximum


def validate_modular_roundtrip(plan, spec, path, expected):
    """Validate raw binds/extras and imported per-region rest and compound skin."""
    raw = _raw_bindings(path, spec, expected)
    raw_joint_rest = raw.pop("_joint_rest_matrices")
    all_points = tuple(point for data in expected["rest"].values() for point in data["points"])
    extent = max(max(point[axis] for point in all_points) - min(point[axis] for point in all_points) for axis in range(3))
    tolerance = max(extent, 1.0e-6) * POSITION_TOLERANCE
    from .blender_export import _capture_state, _restore_state

    snapshot = snapshot_blender_data()
    state = _capture_state(plan)
    try:
        if "FINISHED" not in bpy.ops.import_scene.gltf(filepath=str(path), bone_heuristic="TEMPERANCE"):
            raise RuntimeError("Modular GLB round-trip import failed.")
        objects = tuple(obj for obj in bpy.data.objects if obj not in snapshot.objects)
        armatures = tuple(obj for obj in objects if obj.type == "ARMATURE")
        meshes = tuple(obj for obj in objects if obj.type == "MESH")
        if len(armatures) != 1 or len(meshes) != len(spec.regions):
            raise ValueError("Modular GLB changed its armature or region mesh inventory.")
        rig = armatures[0]
        members = {obj.get(REGION_ID_KEY): (obj, tuple(range(len(obj.data.polygons)))) for obj in meshes}
        if set(members) != set(expected["rest"]) or len(members) != len(meshes):
            raise ValueError("Modular imported meshes lost their unique stable IDs.")
        for region in spec.regions:
            obj = members[region.id][0]
            if obj.get(REGION_ROLE_KEY) != region.role or obj.get(SEAM_POLICY_KEY) != SEAM_POLICY:
                raise ValueError("Modular imported region changed its role or seam policy.")
            active = [modifier for modifier in obj.modifiers if modifier.type == "ARMATURE"]
            if len(active) != 1 or active[0].object is not rig:
                raise ValueError("Modular imported region is not bound to the common armature.")
        hierarchy = {bone.name: bone.parent.name if bone.parent else None for bone in rig.data.bones}
        if hierarchy != expected["hierarchy"]:
            raise ValueError("Modular imported GLB changed the bone hierarchy.")
        with sample_state(meshes, rig) as ids:
            _reset(ids, rig)
            rig.data.pose_position = "REST"
            bpy.context.view_layer.update()
            rest = _region_samples(members, rig)
            rest_errors, attribute_errors, weight_errors, corner_metrics = {}, {}, {}, {}
            for key, (obj, faces) in members.items():
                rest_errors[key] = _surface_error(expected["rest"][key]["points"], rest[key]["points"])
                try:
                    attribute_errors[key] = _corner_error(expected["corners"][key], _corner_records(obj, set(faces)), tolerance,
                                                          report=corner_metrics)
                except ValueError as exc:
                    raise ValueError(f"Modular region {key!r}: {exc}") from exc
                weight_errors[key] = _weight_error(expected["rest"][key]["skin"], rest[key]["skin"], tolerance)
            rig.data.pose_position = "POSE"
            rig_inverse = rig.matrix_world.inverted()
            # Importer bone display axes may differ. Transfer the source world
            # deformation delta, not Euler channels in incompatible local axes.
            pending = set(rig.pose.bones.keys())
            while pending:
                ready = [name for name in pending if rig.pose.bones[name].parent is None
                         or rig.pose.bones[name].parent.name not in pending]
                if not ready:
                    raise ValueError("Modular imported bone hierarchy is cyclic.")
                for name in ready:
                    bone = rig.pose.bones[name]
                    delta = _matrix(expected["joint_pose"][name]) @ _matrix(expected["joint_rest"][name]).inverted()
                    bone.matrix = rig_inverse @ delta @ rig.matrix_world @ bone.bone.matrix_local
                    pending.remove(name)
                    bpy.context.view_layer.update()
            compound = _region_samples(members, rig)
            pose_errors = {key: _surface_error(expected["compound"][key]["points"], compound[key]["points"])
                           for key in members}
            socket_compound_error = 0.0
            for socket in spec.sockets:
                bone = rig.pose.bones[socket.parent_bone]
                imported_rest = rig.matrix_world @ bone.bone.matrix_local
                imported_pose = rig.matrix_world @ bone.matrix
                gltf_delta = _AXES @ imported_pose @ imported_rest.inverted() @ _AXES.inverted()
                rotation = socket.rotation
                local = Matrix.LocRotScale(Vector(socket.translation), Quaternion((rotation[3], *rotation[:3])), Vector(socket.scale))
                actual_socket = gltf_delta @ _matrix(raw_joint_rest[socket.parent_bone]) @ local
                source_socket = _AXES @ _matrix(expected["joint_pose"][socket.parent_bone]) @ local
                socket_compound_error = max(socket_compound_error, _matrix_error(actual_socket, source_socket))
            hide_errors = {}
            for hidden_id in sorted(members):
                hidden_obj = members[hidden_id][0]
                saved = hidden_obj.hide_get()
                try:
                    hidden_obj.hide_set(True)
                    bpy.context.view_layer.update()
                    visible = _region_samples({key: value for key, value in members.items() if key != hidden_id}, rig)
                    hide_errors[hidden_id] = {key: _surface_error(compound[key]["points"], value["points"])
                                              for key, value in visible.items()}
                finally:
                    hidden_obj.hide_set(saved)
                    bpy.context.view_layer.update()
            all_hide_errors = [error for errors in hide_errors.values() for error in errors.values()]
            if max((*rest_errors.values(), *pose_errors.values(), *all_hide_errors), default=0.0) > tolerance:
                raise ValueError("Modular GLB changed region rest, compound deformation or hide independence.")
            if max(weight_errors.values(), default=0.0) > WEIGHT_TOLERANCE:
                raise ValueError("Modular GLB changed common-rig skin weights.")
            if socket_compound_error > ATTRIBUTE_TOLERANCE:
                raise ValueError("Modular GLB changed a socket transform on the actually posed imported joint.")
        return {"schema_version": 1, "passed": True, "region_count": len(members),
                "socket_count": len(spec.sockets), "position_tolerance": tolerance,
                "uv_tolerance": ATTRIBUTE_TOLERANCE, "imported_normal_tolerance": IMPORTED_NORMAL_TOLERANCE,
                "color_tolerance": COLOR_TOLERANCE,
                "max_rest_error": max(rest_errors.values(), default=0.0),
                "max_compound_deformation_error": max(pose_errors.values(), default=0.0),
                "max_corner_attribute_error": max(attribute_errors.values(), default=0.0),
                "max_imported_normal_error": corner_metrics.get("max_normal_error", 0.0),
                "max_imported_uv_error": corner_metrics.get("max_uv_error", 0.0),
                "max_imported_color_error": corner_metrics.get("max_color_error", 0.0),
                "max_weight_error": max(weight_errors.values(), default=0.0),
                "hide_independence_by_region": hide_errors,
                "max_hide_independence_error": max(all_hide_errors, default=0.0),
                "max_socket_compound_error": socket_compound_error,
                "max_socket_rest_and_compound_error": max(raw["max_socket_rest_error"], socket_compound_error),
                "sampling": "unmodified source rest corners and deterministic all-joint compound pose",
                "seam_policy": SEAM_POLICY, "scope": "source-to-modular-export fidelity; not anatomical certification", **raw}
    finally:
        cleanup_imported_data(snapshot)
        _restore_state(state)


__all__ = ("capture_modular_expectation", "validate_modular_roundtrip")
