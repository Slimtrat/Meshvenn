"""Prepared editable authority, no implicit migration, prepublication rollback."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=repository)
    parser.add_argument("--fixture", type=Path, default=repository / "example/v2/modular/StytchDoll")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root, fixture, output = args.package_root.resolve(), args.fixture.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty smoke directory.")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("source.blend", "authoring.json"):
        shutil.copy2(fixture / name, output / name)
    sys.path.insert(0, str(root.parent))
    sys.path.insert(0, str(repository))
    package = importlib.import_module(root.name)
    package.register()

    def module(name):
        return importlib.import_module(f"{root.name}.{name}")

    try:
        bpy.ops.wm.open_mainfile(filepath=str(output / "source.blend"), use_scripts=False)
        api = module("implementations.glb_export.modular_source")
        authoring = module("implementations.authored_source")
        implementation = module("implementations.glb_export.implementation")
        publishing = module("implementations.glb_export.blender_export")
        pipeline = module("core.pipeline_contracts")
        destination = output / "candidate.glb"

        def load(**kwargs):
            return api.context_from_authored_scene(bpy.context.scene, output_path=destination,
                                                   overwrite_existing=True, **kwargs)

        def references():
            return {obj.name: obj.get(api.CATALOGUE_REFERENCE) for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}

        def texts():
            return {item.name: (item.as_string(), dict(item.items())) for item in bpy.data.texts}

        original_refs, original_texts = references(), texts()
        context = load()
        state = context.prepared_modular_source
        assert not state.staged and references() == original_refs and texts() == original_texts
        # The existing editor has an explicit preparation action, separate from export.
        runtime = module("operators.runtime_state")
        runtime._LAST_PIPELINE_CONTEXTS[runtime._scene_key(bpy.context.scene)] = context
        bpy.context.scene.bpt_settings.export_output_path = str(destination)
        bpy.context.scene.bpt_settings.export_overwrite_existing = True
        assert bpy.ops.bpt.prepare_modular_source(replace_existing=True) == {"FINISHED"}
        state = context.prepared_modular_source
        assert not state.staged and references() == original_refs and texts() == original_texts
        mesh = context.require_output(pipeline.PipelineStage.GEOMETRY).blender_object
        rig = context.require_output(pipeline.PipelineStage.RIG).armature_object
        from scripts.author_stytch_doll import source_snapshot
        authority = source_snapshot(mesh, rig)
        exporter = implementation.GLBExportImplementation()

        def failed(candidate, expected):
            result = exporter.execute(candidate)
            assert result.failed and expected.lower() in result.message.lower(), result.message
            assert source_snapshot(mesh, rig) == authority
            return result

        context.prepared_modular_source = None
        with patch.object(authoring, "prepare_authored_source", side_effect=AssertionError("No implicit preparation")):
            failed(context, "prepared editable state")
        assert not destination.exists() and texts() == original_texts and references() == original_refs
        context.prepared_modular_source = state
        geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
        context.set_output(pipeline.PipelineStage.GEOMETRY, replace(geometry, metadata={"changed": True}))
        # The rig must still belong to the exact Geometry; no value-based aliasing.
        failed(context, "current geometry")
        context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
        altered = state.plan.modular_spec.to_dict()
        altered["sockets"][0]["translation"][0] += .01
        context.metadata.pop("export_modular_manifest_path")
        context.metadata["export_modular_spec"] = altered
        failed(context, "stale")
        context = load()

        # A prepared saved source does not allocate, prepare or initialize during export.
        with ExitStack() as guards:
            for owner, name in ((authoring, "prepare_authored_source"),
                                (authoring, "stage_authored_scene_catalogue"),
                                (api, "stage_authored_scene_catalogue"), (api, "_initial_static_catalogue")):
                guards.enter_context(patch.object(owner, name, side_effect=AssertionError("Export must only consume prepared authority")))
            result = exporter.execute(context)
        assert result.success, result.message
        assert texts() == original_texts and references() == original_refs
        assert source_snapshot(mesh, rig) == authority
        previous_glb = destination.read_bytes()

        # Missing historical authority is not repaired by ordinary loading or export.
        previous_reference = mesh.pop(api.CATALOGUE_REFERENCE)
        try:
            load()
        except ValueError as exc:
            assert api.CATALOGUE_REFERENCE in str(exc)
        else:
            raise AssertionError("Ordinary loading implicitly initialized historical source.")
        absent_refs = references()

        def initialize():
            candidate = load(initialize_static_source=True, binding_method="canonical-envelope-v2")
            assert candidate.prepared_modular_source.staged
            assert references() == absent_refs
            assert set(texts()) - set(original_texts) == {candidate.prepared_modular_source.saved_text.name}
            return candidate

        context = initialize()
        with patch.object(authoring, "commit_authored_scene_catalogue", side_effect=RuntimeError("Injected catalogue commit failure")):
            failed(context, "catalogue commit failure")
        assert references() == absent_refs and texts() == original_texts
        assert destination.read_bytes() == previous_glb

        context = initialize()
        original_commit = authoring.commit_authored_scene_catalogue

        def partial_commit_failure(plan, staged):
            original_commit(plan, staged)
            raise RuntimeError("Injected partial catalogue commit failure")

        with patch.object(authoring, "commit_authored_scene_catalogue", side_effect=partial_commit_failure):
            failed(context, "partial catalogue commit failure")
        assert references() == absent_refs and texts() == original_texts
        assert destination.read_bytes() == previous_glb

        context = initialize()

        def publication_failure(*args, **kwargs):
            assert mesh[api.CATALOGUE_REFERENCE] == context.prepared_modular_source.saved_text.name
            assert context.prepared_modular_source.saved_text["meshvenn_catalogue_committed"] is True
            raise RuntimeError("Injected atomic publication failure")

        with patch.object(publishing, "_publish_validated_glb", side_effect=publication_failure):
            failed(context, "atomic publication failure")
        assert references() == absent_refs and texts() == original_texts
        assert destination.read_bytes() == previous_glb

        # Failure before fidelity also discards authoring-owned pending Texts.
        context = initialize()
        context.prepared_modular_source.plan = replace(context.prepared_modular_source.plan, modular_spec=None)
        failed(context, "stale")
        assert references() == absent_refs and texts() == original_texts
        assert destination.read_bytes() == previous_glb

        # A preparation abandoned by rebuilding/clearing runtime owns its cleanup.
        context = initialize()
        runtime._LAST_PIPELINE_CONTEXTS[runtime._scene_key(bpy.context.scene)] = context
        runtime.clear_pipeline_runtime_state(bpy.context.scene)
        assert references() == absent_refs and texts() == original_texts

        context = initialize()
        result = exporter.execute(context)
        assert result.success, result.message
        assert mesh[api.CATALOGUE_REFERENCE] != previous_reference
        assert all(texts().get(name) == value for name, value in original_texts.items()), "Existing Text content changed."
        assert source_snapshot(mesh, rig) == authority
        reopened = load()
        assert not reopened.prepared_modular_source.staged
        assert not reopened.has_output(pipeline.PipelineStage.MOTION)
        assert not list(output.glob("*.tmp.glb"))
        (output / "report.json").write_text(json.dumps({"passed": True,
            "ordinary_export_has_no_authoring_mutations": True,
            "missing_or_stale_state_rejected": True, "commit_failure_rollback": True,
            "publication_failure_rollback": True, "historical_initialization_explicit": True,
            "source_authority_unchanged": True, "zero_clips": True}, indent=2), "utf-8")
        print("Prepared editable authority PASS: no implicit migration; stale state rejected; catalogue/publication rollback.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
