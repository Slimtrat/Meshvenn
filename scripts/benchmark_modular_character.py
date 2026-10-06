"""Generate a real native V2 character, export modular regions, and certify fidelity."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

from scripts.benchmark_character_v2 import _export_unrigged_reference
from scripts.benchmark_glb_v2 import create_blank_template, render_projection
from scripts.generate_example_native_support.extraction import extract_sheet
from scripts.glb_v2_character_support import connectivity_summary
from scripts.modular_character_authoring import author_fixture_spec
from scripts.run_logger import RunLogger
from scripts.render_material_projections import render_material_projections
from scripts.modular_character_appearance import prepare_appearance, save_appearance_provenance
from scripts.modular_appearance_evidence import certify_appearance
from scripts.material_color_transport import certify_material_color_transport


def _module(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def _stage(context, stage, implementation):
    selections = _module("properties.pipeline")
    selections.ensure_pipeline_defaults(context.settings)
    selections.set_pipeline_implementation(context.settings, stage, implementation.descriptor.identifier)
    selections.pipeline_stage_settings(context.settings, stage).enabled = True
    result = implementation.execute(context)
    if not result.success:
        raise AssertionError(f"Modular fixture {stage.name}: {result.message}")
    context.set_output(stage, result.payload)
    return result


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=64)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not 32 <= args.resolution <= 256:
        raise ValueError("Modular fixture resolution must be between 32 and 256.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "example/v2/assets/UAL1_Standard.glb"
    isolated = output / "reference_unrigged.glb"
    _, _, isolation, _ = _export_unrigged_reference(source, isolated)
    template, sheet = output / "template.png", output / "source_sheet.png"
    create_blank_template(template, width=3000, height=1800)
    render_projection(isolated, template, sheet)
    views, _ = extract_sheet(sheet, output / "views", white_threshold=.94,
                             alpha_threshold=.1, logger=RunLogger())
    if len(views) != 10 or not all(view.valid for view in views):
        raise AssertionError("Modular fixture requires all ten calibrated source views.")
    color_transport = certify_material_color_transport(output / "appearance/color_transport", _module)
    color_views, appearance_provenance = render_material_projections(isolated, output / "appearance/views")
    appearance_provenance["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    geometry_input = {"mode": "neutral-silhouette", "sheet_sha256": hashlib.sha256(sheet.read_bytes()).hexdigest(),
                      "views": [{"name": view.name, "sha256": hashlib.sha256(view.path.read_bytes()).hexdigest()}
                                for view in views]}
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        settings = bpy.context.scene.bpt_settings
        settings.resolution = args.resolution
        settings.normalize_height = True
        settings.target_height = 2
        settings.surface_refinement = "organic"
        settings.uv_bake_texture_size = "512"
        settings.uv_bake_samples_per_axis = "2"
        settings.projections.clear()
        for view in views:
            projection = settings.projections.add()
            projection.name = view.name
            projection.image = bpy.data.images.load(str(view.path.resolve()))
            projection.azimuth = math.radians(view.azimuth_degrees)
            projection.elevation = math.radians(view.elevation_degrees)
        pipeline = _module("core.pipeline_contracts")
        context = pipeline.PipelineContext(scene=bpy.context.scene, settings=settings)
        stage = pipeline.PipelineStage
        prepared = _stage(context, stage.INPUT, _module("implementations.projection_images").ProjectionImagesImplementation())
        geometry_result = _stage(context, stage.GEOMETRY, _module("implementations.native_visual_hull").NativeVisualHullImplementation())
        context.material_input, source_signals = prepare_appearance(
            geometry_result.payload, color_views, appearance_provenance, _module)
        material = _stage(context, stage.MATERIAL, _module("implementations.uv_bake").UVBakeImplementation())
        appearance = certify_appearance(material.payload.bake_result,
                                        context.metadata["material_sampling_diagnostics"], source_signals)
        appearance.update(appearance_provenance)
        appearance.update(atlas_storage="srgb-byte-from-scene-linear", color_transport=color_transport)
        save_appearance_provenance(appearance)
        rig_result = _stage(context, stage.RIG, _module("implementations.canonical_rig_v2").CanonicalRigV2Implementation())
        context.metadata["motion_source_path"] = str(source)
        motion = _stage(context, stage.MOTION, _module("implementations.canonical_motion").CanonicalMotionRetargetImplementation())
        geometry, rig = geometry_result.payload, rig_result.payload
        source_connectivity = connectivity_summary(
            [tuple(vertex.co) for vertex in geometry.blender_object.data.vertices],
            [tuple(face.vertices) for face in geometry.blender_object.data.polygons])
        if source_connectivity["component_count"] != 1:
            raise AssertionError("The modular humanoid fixture must not contain detached fragments.")
        if len(rig.armature_object.data.bones) != 18:
            raise AssertionError("Modular fixture must retain the native eighteen-joint rig.")
        contract = _module("core.modular_character")
        spec, choices = author_fixture_spec(geometry, rig, contract)
        _write_json(output / "authoring.json", spec.to_dict())
        _write_json(output / "partition-authoring.json", choices)
        text = bpy.data.texts.new("meshvenn-modular-authoring.json")
        text.write(json.dumps(spec.to_dict(), indent=2))
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True)
        context.metadata.update(export_modular_spec=spec, export_output_path=str(output / "character.glb"),
                                export_overwrite_existing=True, export_validate_roundtrip=True)
        exported = _stage(context, stage.EXPORT, _module("implementations.glb_export").GLBExportImplementation()).payload
        metadata_module = _module("implementations.glb_export.modular_gltf")
        document, _ = metadata_module.read_glb(exported.path)
        envelope = document["asset"]["extras"]["meshvenn_modular_character"]
        fidelity = exported.metadata["roundtrip"]["modular_character"]
        # Keep editable parts AND the hidden, authoritative original surface.
        # Socket metadata does not create any new deforming bone.
        plan = _module("implementations.glb_export.planning").build_export_plan(context)
        with _module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan, spec):
            geometry.blender_object.hide_render = True
            geometry.blender_object.hide_set(True)
            settings.export_output_path = "//character.glb"
            settings.export_modular_character = True
            settings.export_modular_manifest_path = "//authoring.json"
            bpy.ops.file.pack_all()
            result = bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True)
            if "FINISHED" not in result:
                raise AssertionError("Could not save the editable modular source.")
        manifest = {"schema_version": 1, "artifact": "character.glb", "sha256": exported.sha256,
                    "editable_source": "source.blend", "editable_source_sha256": hashlib.sha256(
                        (output / "source.blend").read_bytes()).hexdigest(),
                    "authoring": "authoring.json", "contract": envelope,
                    "source_asset": "quaternius_ual1", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "source_license": "CC0-1.0", "source_credit": "Quaternius (reference model and source animations)",
                    "pipeline": ["isolated source rest mesh", "ten calibrated views", "native-visual-hull",
                                 "uv-bake-v2", "canonical-biped-v2", "canonical-motion-retarget-v1", "modular GLB"],
                    "source_rig_isolation": isolation, "resolution": args.resolution,
                    "source_connectivity": source_connectivity,
                    "surface_refinement": geometry.metadata["surface_refinement"],
                    "material": material.metrics, "native_joint_count": 18,
                    "geometry_input_mode": "neutral-silhouette", "geometry_input": geometry_input,
                    "material_input_mode": "source-color-projection", "appearance": appearance,
                    "surface_representation": "authoritative-source-Blender-loop-triangles; no caps or additional surface",
                    "animation_count": len(exported.animation_names), "partition_authoring": choices,
                    "roundtrip": fidelity, "consumer_acceptance": "Godot/Stytch gates are separate and not certified here"}
        _write_json(output / "manifest.json", manifest)
        print(f"Modular character: {len(spec.regions)} regions, {len(spec.sockets)} sockets, "
              f"18 native joints, {len(exported.animation_names)} clips; all fidelity gates PASS")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
