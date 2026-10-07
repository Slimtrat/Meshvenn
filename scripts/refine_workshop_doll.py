"""Publish a distinct head-isolated doll variant; never overwrite the accepted baseline."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from scripts.author_stytch_doll import (assert_source_unchanged, digest, module,
                                       remove_saved_previews, source_snapshot, write_json)
from scripts.workshop_doll_evidence import compare_head_variant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "example/v2/modular/StytchDoll")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    fixture, output = args.fixture.resolve(strict=True), args.output.resolve()
    baseline = json.loads((fixture / "manifest.json").read_text("utf-8"))
    if (digest(fixture / "character.glb") != baseline["sha256"]
            or digest(fixture / "source.blend") != baseline["editable_source_sha256"]):
        raise ValueError("Baseline bundle hashes do not match the accepted fixture.")
    if output == fixture or fixture in output.parents or (output.exists() and any(output.iterdir())):
        raise ValueError("Choose a separate empty variant directory; the baseline is immutable.")
    output.mkdir(parents=True, exist_ok=True)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(fixture / "source.blend"), use_scripts=False)
        mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
        old = source_snapshot(mesh, rig)
        spec = module("implementations.glb_export.face_authoring")._read(fixture / "authoring.json")
        remove_saved_previews(mesh, spec)
        mesh.hide_set(False)
        mesh.hide_render = False
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        assert bpy.ops.bpt.refine_head_weights() == {"FINISHED"}
        edit = json.loads(mesh["meshvenn_head_isolation"])
        refined = source_snapshot(mesh, rig)
        assert old["weights"] != refined["weights"]
        assert {k: v for k,v in old.items() if k != "weights"} == {k: v for k,v in refined.items() if k != "weights"}
        for name in ("authoring.json", "partition-authoring.json", "reference.glb"):
            shutil.copy2(fixture / name, output / name)
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_character = True
        settings.export_modular_manifest_path = str(output / "authoring.json")
        settings.export_output_path = str(output / "character.glb")
        settings.export_overwrite_existing = False
        forbidden = (("implementations.projection_images", "ProjectionImagesImplementation"),
                     ("implementations.native_visual_hull", "NativeVisualHullImplementation"),
                     ("implementations.uv_bake", "UVBakeImplementation"),
                     ("implementations.canonical_rig_v2", "CanonicalRigV2Implementation"),
                     ("implementations.canonical_motion", "CanonicalMotionRetargetImplementation"))
        with ExitStack() as guards:
            for name, cls in forbidden:
                guards.enter_context(patch.object(getattr(module(name), cls), "execute",
                                                  side_effect=AssertionError("Variant export rebuilt a stage.")))
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        assert_source_unchanged(refined, source_snapshot(mesh, rig), output)
        context = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        exported = context.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
        reader = module("implementations.glb_export.modular_gltf")
        document, binary = reader.read_glb(exported.path)
        reference, reference_binary = reader.read_glb(fixture / "reference.glb")
        # The pinned exporter bakes inherited normalization into POSITION.
        # Translate native-Z observation into decoded glTF-Y accessor units;
        # do not compare metre coordinates against unnormalized scan units.
        positions = [p for m in reference["meshes"] for primitive in m["primitives"]
                     for p in reader.read_accessor(reference, reference_binary, primitive["attributes"]["POSITION"])]
        low, high = min(p[1] for p in positions), max(p[1] for p in positions)
        native_low, native_high = min(v.co.z for v in mesh.data.vertices), max(v.co.z for v in mesh.data.vertices)
        scale = (high-low)/(native_high-native_low)
        accessor_envelope = {**edit["envelope"], **{
            key: low+(edit["envelope"][key]-native_low)*scale for key in ("start_z", "end_z", "neck_z")}}
        proof = compare_head_variant(reference, reference_binary, document, binary, reader.read_accessor, accessor_envelope)
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        plan = module("implementations.glb_export.planning").build_export_plan(
            module("implementations.glb_export.modular_source").context_from_authored_scene(
                bpy.context.scene, output_path=str(output / "preview-only.glb")))
        with module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan, spec):
            mesh.hide_set(True)
            mesh.hide_render = True
            bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True, relative_remap=False)
        manifest = {**baseline, "source_asset": "stytch_workshop_doll_head_isolated_v1",
                    "sha256": exported.sha256, "editable_source_sha256": digest(output / "source.blend"),
                    "contract": document["asset"]["extras"]["meshvenn_modular_character"],
                    "pipeline": "accepted native source -> explicit head weights edit -> No Rebuild modular export",
                    "source_authority_unchanged": False, "selected_refined_source_unchanged_during_export": True,
                    "source_authority_sha256": hashlib.sha256(json.dumps(refined, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                    "baseline_artifact_sha256": baseline["sha256"], "head_refinement": edit,
                    "glb_accessor_head_envelope": accessor_envelope,
                    "reference_role": "Accepted baseline with OLD weights, not the new weight fidelity oracle",
                    "reference_fidelity": proof, "roundtrip": exported.metadata["roundtrip"]["modular_character"],
                    "consumer_acceptance": "New variant has NOT been replayed by Stytch; accepted baseline remains separate.",
                    "remaining_limits": ["Existing canonical head/neck pivots were not refitted; neck bending remains unqualified.",
                                         "Original two-view atlas coverage and UV overlap unchanged; artistic quality unqualified."]}
        write_json(output / "manifest.json", manifest)
        print(f"Head variant PASS: {edit['changed_vertex_count']} weights edited; source surface, atlas and eighteen rest joints unchanged.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
