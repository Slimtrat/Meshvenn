"""Author the cloth LOD's explicit regions/sockets, then use the normal exporter.

The planes and landmark targets below are design choices for this exact asset,
not anatomical inference or ownership from skin influences. Export replays the
frozen face/vertex choices and refuses changed geometry.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender import source
from scripts.author_stytch_doll import source_snapshot
from scripts.cloth_lod import REFERENCE_SHA256, write_json

REGIONS = ("body-core", "left-arm", "right-arm", "left-leg", "right-leg")
AXES = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
# Native source coordinates in metres. Orientations are authored in glTF world.
CUTS = {
    "arm_left_x": 0.200,
    "arm_right_x": -0.188,
    "arm_min_z": 1.15,
    "arm_max_z": 1.46,
    "hip_z": 0.845,
    "center_x": 0.005942434,
}
LANDMARKS = (
    ("head", "head", "body-core", (0.006, 0, 1.882)),
    ("left-arm", "hand.L", "left-arm", (0.81, -0.035, 1.335)),
    ("right-arm", "hand.R", "right-arm", (-0.80, -0.035, 1.329)),
    ("left-leg", "foot.L", "left-leg", (0.166, -0.230, 0.145)),
    ("right-leg", "foot.R", "right-leg", (-0.166, -0.230, 0.145)),
    ("back", "chest", "body-core", (0.006, 0.18, 1.35)),
    ("wing", "chest", "body-core", (0.006, 0.15, 1.41)),
    ("backpack", "spine", "body-core", (0.006, 0.18, 1.20)),
)


def api(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def fingerprint(mesh):
    return api("core.modular_character").mesh_surface_sha256(
        [tuple(v.co) for v in mesh.data.vertices],
        [tuple(p.vertices) for p in mesh.data.polygons],
    )


def draft_authoring(mesh, source_sha):
    """Freeze this fixture's whole-face choices; no classifier runs at export."""
    owners = []
    for polygon in mesh.data.polygons:
        x, _, z = tuple(
            sum(mesh.data.vertices[i].co[a] for i in polygon.vertices)
            / len(polygon.vertices)
            for a in range(3)
        )
        if z < CUTS["hip_z"]:
            role = "left-leg" if x >= CUTS["center_x"] else "right-leg"
        elif CUTS["arm_min_z"] <= z <= CUTS["arm_max_z"] and x > CUTS["arm_left_x"]:
            role = "left-arm"
        elif CUTS["arm_min_z"] <= z <= CUTS["arm_max_z"] and x < CUTS["arm_right_x"]:
            role = "right-arm"
        else:
            role = "body-core"
        owners.append(role)
    eligible = {r: set() for r in REGIONS}
    for polygon, role in zip(mesh.data.polygons, owners):
        eligible[role].update(polygon.vertices)
    landmarks = []
    for role, bone, region, target in LANDMARKS:
        index = min(
            eligible[region],
            key=lambda i: ((mesh.data.vertices[i].co - Vector(target)).length, i),
        )
        landmarks.append(
            {
                "role": role,
                "bone": bone,
                "region": region,
                "vertex_index": index,
                "world_rotation_xyzw": [0, 0, 0, 1],
                "authoring_target_native_m": target,
            }
        )
    return {
        "schema_version": 1,
        "asset_family": "stytch-dummy-cloth",
        "source_blend_sha256": source_sha,
        "source_surface_sha256": fingerprint(mesh),
        "source_object": mesh.name,
        "design_planes_native_m": CUTS,
        "scope": "Fixture-specific producer authoring, not inferred anatomy or physical ownership",
        "owners": owners,
        "socket_landmarks": landmarks,
        "seams": "open-shared-vertices",
        "caps": 0,
    }


def author_spec(mesh, rig, plan, source_sha):
    contract = api("core.modular_character")
    if (
        plan["schema_version"] != 1
        or plan["source_blend_sha256"] != source_sha
        or plan["source_object"] != mesh.name
        or plan["source_surface_sha256"] != fingerprint(mesh)
    ):
        raise ValueError("Authoring choices do not name this exact source surface")
    owners = tuple(plan["owners"])
    if len(owners) != len(mesh.data.polygons) or set(owners) != set(REGIONS):
        raise ValueError(
            "Every source face must have exactly one of the five nonempty owners"
        )
    normalization = api("implementations.glb_export.modular_source")._normalization(
        mesh
    )
    sockets, anchors = [], []
    declarations = {role: (bone, region) for role, bone, region, _ in LANDMARKS}
    if len(plan["socket_landmarks"]) != 8 or {
        x["role"] for x in plan["socket_landmarks"]
    } != set(declarations):
        raise ValueError("Require exactly the eight authored attachment roles")
    for landmark in plan["socket_landmarks"]:
        role, bone, region = landmark["role"], landmark["bone"], landmark["region"]
        if (bone, region) != declarations[role]:
            raise ValueError("Socket parent/region contradicts cloth authoring")
        index = landmark["vertex_index"]
        if type(index) is not int or not 0 <= index < len(mesh.data.vertices):
            raise ValueError("Invalid source landmark vertex")
        if not any(
            index in p.vertices and owner == region
            for p, owner in zip(mesh.data.polygons, owners)
        ):
            raise ValueError("Socket landmark is outside its declared region")
        rotation = landmark["world_rotation_xyzw"]
        if rotation != [0, 0, 0, 1]:
            raise ValueError(
                "This authored fixture uses the glTF world equipment orientation"
            )
        point = AXES @ mesh.matrix_world @ mesh.data.vertices[index].co
        desired = Matrix.Translation(point)
        parent = AXES @ rig.matrix_world @ rig.data.bones[bone].matrix_local
        translation, quaternion, scale = (parent.inverted() @ desired).decompose()
        quaternion.normalize()
        socket = contract.SocketSpec(
            "attach-" + role,
            role,
            bone,
            region,
            tuple(translation),
            (quaternion.x, quaternion.y, quaternion.z, quaternion.w),
            tuple(scale),
        )
        sockets.append(socket)
        anchors.append(
            {
                "role": role,
                "source_vertex_index": index,
                "authored_gltf_world_matrix": [list(r) for r in desired],
            }
        )
    spec = contract.ModularCharacterSpec(
        rig_id="canonical-biped-v2",
        rig_version=2,
        coordinates=contract.CoordinateConvention(
            contract.NormalizationConvention(
                normalization.normalized_height,
                normalization.target_height,
                normalization.scale,
            )
        ),
        regions=tuple(
            contract.RegionSpec(r, r, "Cloth_" + r.replace("-", "_")) for r in REGIONS
        ),
        ownership={mesh.name: owners},
        ownership_source_sha256={mesh.name: fingerprint(mesh)},
        seams=contract.SeamDeclarations(),
        sockets=tuple(sockets),
    )
    return spec, anchors, normalization


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--lod-report", type=Path, required=True)
    parser.add_argument("--pose-report", type=Path, required=True)
    parser.add_argument(
        "--authoring",
        type=Path,
        help="Frozen choices; omit only with --draft-authoring",
    )
    parser.add_argument("--draft-authoring", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    original = args.source.resolve(strict=True)
    report = json.loads(args.lod_report.read_text("utf-8"))
    original_sha = source.digest(original)
    pose_report = json.loads(args.pose_report.read_text("utf-8"))
    if (
        pose_report["candidate_sha256"] != original_sha
        or not pose_report["fidelity_passed"]
    ):
        raise ValueError("LOD did not pass the frozen source/pose fidelity budgets")
    if (
        report["candidate_blend_sha256"] != original_sha
        or not report["rest_fidelity_passed"]
        or report["reference_glb_sha256"] != REFERENCE_SHA256
    ):
        raise ValueError("LOD source is unverified or no longer matches its receipt")
    if bool(args.authoring) == bool(args.draft_authoring):
        raise ValueError(
            "Choose either frozen --authoring or the explicit --draft-authoring operation"
        )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        mesh, rig = source.load(original)
        plan = (
            draft_authoring(mesh, original_sha)
            if args.draft_authoring
            else json.loads(args.authoring.read_text("utf-8"))
        )
        write_json(output / "partition-authoring.json", plan)
        spec, anchors, normalization = author_spec(mesh, rig, plan, original_sha)
        write_json(output / "authoring.json", spec.to_dict())
        before = source_snapshot(mesh, rig)
        pipeline = api("core.pipeline_contracts")
        geometry_api = api("core.geometry_contracts")
        geometry = geometry_api.GeometrySurfaceOutput(
            mesh,
            SimpleNamespace(material_views=None),
            api("implementations.glb_export.modular_source")._projection_space(mesh),
            "native-visual-hull",
            normalization=normalization,
            metadata={"source": "explicit-cloth-source-lod-authoring"},
        )
        rig_output = api("core.rig_contracts").RigOutput(
            geometry,
            mesh,
            rig,
            "canonical-biped-v2",
            {b.name: b.name for b in rig.data.bones},
            "cloth-source-deformation-protected-collapse-v5",
        )
        context = pipeline.PipelineContext(
            scene=bpy.context.scene,
            metadata={
                "export_output_path": str(output / "character.glb"),
                "export_overwrite_existing": False,
                "export_validate_roundtrip": True,
                "export_modular_spec": spec,
            },
        )
        context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
        context.set_output(pipeline.PipelineStage.RIG, rig_output)
        api("implementations.glb_export.face_authoring").load_face_ownership(mesh, spec)
        api("implementations.authored_source").prepare_authored_source(context)
        result = (
            api("implementations.glb_export").GLBExportImplementation().execute(context)
        )
        if not result.success:
            raise RuntimeError(result.message)
        if source_snapshot(mesh, rig) != before:
            raise ValueError("Modular publication changed source authority")
        document, _ = api("implementations.glb_export.modular_gltf").read_glb(
            output / "character.glb"
        )
        triangles = sum(
            document["accessors"][p["indices"]]["count"] // 3
            for m in document["meshes"]
            for p in m["primitives"]
        )
        if (
            len(document["meshes"]) != 5
            or len(document["skins"][0]["joints"]) != 18
            or triangles > 18000
            or document.get("animations")
        ):
            raise ValueError("Export violates the cloth modular delivery contract")
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_character = True
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        # Keep packed images portable. Do not unpack, rebake or resample pixels.
        for image in bpy.data.images:
            if (
                image.users
                and image.type != "RENDER_RESULT"
                and image.size[0] > 0
                and image.packed_file is None
            ):
                image.pack()
        bpy.ops.wm.save_as_mainfile(
            filepath=str(output / "source.blend"), compress=True
        )
        manifest = {
            "schema_version": 1,
            "asset_id": "stytch-dummy-cloth-modular-v1",
            "artifact": "character.glb",
            "sha256": source.digest(output / "character.glb"),
            "editable_source": "source.blend",
            "editable_source_sha256": source.digest(output / "source.blend"),
            "lod_input_sha256": original_sha,
            "reference_glb_sha256": REFERENCE_SHA256,
            "triangle_count": triangles,
            "triangle_budget": 18000,
            "native_joint_count": 18,
            "regions": {r: spec.ownership[mesh.name].count(r) for r in REGIONS},
            "socket_authoring": anchors,
            "normalization": normalization.to_dict(),
            "contract": document["asset"]["extras"]["meshvenn_modular_character"],
            "export_roundtrip": result.metadata["roundtrip"],
            "source_authority_unchanged_by_export": True,
            "lod": report,
            "pose_fidelity": pose_report,
            "rights": {
                "explicit_asset_family_grant_recorded": False,
                "consumer_review": "pending",
                "scope": "Repository declaration is not an automatic blanket grant over generated assets or source inputs.",
            },
            "selected": False,
            "visual_acceptance": False,
            "consumer_admission": False,
            "contact_qualified": False,
            "collision_proxies": None,
            "scope": "New producer candidate. Frozen full-body and older skins untouched; pre-existing held/presence creases remain. Consumer native/missing/equipment/walk/leg/physics/rights gates are separate.",
        }
        write_json(output / "manifest.json", manifest)
        if source.digest(original) != original_sha:
            raise ValueError("Immutable LOD input changed")
        print(
            f"Modular producer candidate: {triangles} triangles, 5 regions, 8 sockets; SHA {manifest['sha256']}; NOT admitted"
        )
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
