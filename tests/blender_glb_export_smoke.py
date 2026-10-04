"""Blender smoke test for the built-in static GLB export stage."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _import_package(package_root: Path) -> str:
    root = package_root.resolve()
    _require((root / "__init__.py").is_file(), f"Invalid package root: {root}")
    if str(root.parent) not in sys.path:
        sys.path.insert(0, str(root.parent))
    importlib.import_module(root.name)
    return root.name


def _clear_scene() -> None:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mesh in tuple(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _create_geometry_mesh() -> bpy.types.Object:
    mesh = bpy.data.meshes.new("Maillage Démo GLB")
    mesh.from_pydata(
        (
            (-0.75, -0.50, 0.00),
            (0.75, -0.50, 0.00),
            (0.00, 0.70, 0.00),
            (0.00, 0.00, 1.25),
        ),
        (),
        (
            (0, 2, 1),
            (0, 1, 3),
            (1, 2, 3),
            (2, 0, 3),
        ),
    )
    mesh.validate(verbose=True)
    mesh.update()
    obj = bpy.data.objects.new("Personnage Démo", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


@dataclass(frozen=True)
class _UIState:
    active_object: Any | None
    selected_pointers: frozenset[int]
    frame_current: int


def _capture_ui_state() -> _UIState:
    return _UIState(
        active_object=bpy.context.view_layer.objects.active,
        selected_pointers=frozenset(
            obj.as_pointer() for obj in bpy.context.selected_objects
        ),
        frame_current=bpy.context.scene.frame_current,
    )


def _assert_ui_state(expected: _UIState, *, label: str) -> None:
    actual = _capture_ui_state()
    _require(
        actual.active_object is expected.active_object,
        f"{label}: active object was not restored",
    )
    _require(
        actual.selected_pointers == expected.selected_pointers,
        f"{label}: selection was not restored",
    )
    _require(
        actual.frame_current == expected.frame_current,
        f"{label}: current frame was not restored",
    )


def _temporary_glbs(directory: Path) -> tuple[Path, ...]:
    return tuple(sorted(directory.glob("*.tmp.glb")))


def _validate_static_export(
    result: Any,
    *,
    export_contracts: Any,
    inspect_glb: Any,
    target: Path,
    mesh_object: bpy.types.Object,
) -> tuple[Any, bytes]:
    _require(result.success, f"GLB export failed: {result.message}")
    output = result.payload
    _require(
        isinstance(output, export_contracts.ExportOutput),
        "GLB export did not return ExportOutput",
    )
    _require(output.geometry.blender_object is mesh_object, "Export lost its geometry")
    _require(output.rig is None and output.motion is None, "Static export gained rig data")
    _require(output.path == target.resolve(), "ExportOutput path is incorrect")
    _require(output.object_names == (mesh_object.name,), "Unexpected exported objects")
    _require(not output.animation_names, "Static ExportOutput contains animations")
    _require(target.is_file(), "GLB artifact was not created")

    payload = target.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    _require(output.size_bytes == len(payload) == target.stat().st_size,
             "ExportOutput size does not match the GLB artifact")
    _require(output.sha256 == digest, "ExportOutput SHA-256 does not match the GLB")

    manifest = inspect_glb(target)
    _require(manifest.size_bytes == output.size_bytes, "Manifest size mismatch")
    _require(manifest.sha256 == output.sha256, "Manifest SHA-256 mismatch")
    _require(manifest.version == 2, "Export is not a glTF 2.0 GLB")
    _require(manifest.mesh_count == 1, "Static GLB must contain exactly one mesh")
    _require(manifest.skin_count == 0, "Static GLB unexpectedly contains a skin")
    _require(not manifest.animation_names, "Static GLB unexpectedly contains animation")
    return output, payload


def main() -> None:
    args = _arguments()
    output_root = args.output.resolve()
    target = output_root / "répertoire avec espaces" / "personnage été.glb"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    for temporary in _temporary_glbs(target.parent):
        temporary.unlink()

    package_name = _import_package(args.package_root)
    geometry_contracts = importlib.import_module(
        f"{package_name}.core.geometry_contracts"
    )
    export_contracts = importlib.import_module(f"{package_name}.core.export_contracts")
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    exporter_module = importlib.import_module(
        f"{package_name}.implementations.glb_export"
    )
    manifest_module = importlib.import_module(
        f"{package_name}.implementations.glb_export.manifest"
    )
    planning_module = importlib.import_module(
        f"{package_name}.implementations.glb_export.planning"
    )
    blender_export_module = importlib.import_module(
        f"{package_name}.implementations.glb_export.blender_export"
    )

    _clear_scene()
    mesh_object = _create_geometry_mesh()
    sentinel = bpy.data.objects.new("Sélection témoin", None)
    bpy.context.scene.collection.objects.link(sentinel)
    bpy.ops.object.select_all(action="DESELECT")
    sentinel.select_set(True)
    bpy.context.view_layer.objects.active = sentinel
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 90
    bpy.context.scene.frame_set(37)
    expected_ui_state = _capture_ui_state()

    geometry = geometry_contracts.GeometrySurfaceOutput(
        blender_object=mesh_object,
        source=object(),
        projection_space=geometry_contracts.GeometryProjectionSpace(16, 16, 16),
        implementation_id="glb-export-smoke-geometry",
    )
    context = pipeline.PipelineContext(scene=bpy.context.scene)
    context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
    context.metadata["export_output_path"] = str(target)
    context.metadata["export_overwrite_existing"] = False
    context.metadata["export_validate_roundtrip"] = True
    implementation = exporter_module.GLBExportImplementation()

    availability = implementation.availability(context)
    _require(availability.ready, f"Initial GLB export unavailable: {availability.reason}")
    first_result = implementation.execute(context)
    first_output, first_bytes = _validate_static_export(
        first_result,
        export_contracts=export_contracts,
        inspect_glb=manifest_module.inspect_glb,
        target=target,
        mesh_object=mesh_object,
    )
    _assert_ui_state(expected_ui_state, label="initial export")
    _require(not _temporary_glbs(target.parent), "Initial export leaked a temporary GLB")

    first_hash = hashlib.sha256(first_bytes).hexdigest()
    # Preserve, static and canonical routes all protect their GLB input,
    # independently from the optional Motion source path.
    context.metadata["export_overwrite_existing"] = True
    context.metadata["glb_input_path"] = str(target)
    source_refused = implementation.execute(context)
    _require(source_refused.failed and "source file" in source_refused.message,
             "EXPORT accepted the source GLB as its destination")
    _require(target.read_bytes() == first_bytes, "Source overwrite guard changed input bytes")
    context.metadata.pop("glb_input_path")
    input_contracts = importlib.import_module(f"{package_name}.core.glb_input_contracts")
    typed_source = input_contracts.GLBFileInputOutput(
        path=target, implementation_id="glb-file-v1", size_bytes=first_output.size_bytes,
        sha256=first_hash, node_names=(mesh_object.name,), animation_names=(),
        scene_count=1, mesh_count=1, skin_count=0, material_count=0,
    )
    context.set_output(pipeline.PipelineStage.INPUT, typed_source)
    typed_refused = implementation.execute(context)
    _require(typed_refused.failed and "source file" in typed_refused.message,
             "EXPORT ignored typed input provenance when source metadata was absent")
    context.outputs.pop(pipeline.PipelineStage.INPUT)
    context.metadata["export_overwrite_existing"] = False
    refused_availability = implementation.availability(context)
    _require(
        not refused_availability.available,
        "Existing output should make overwrite-disabled export unavailable",
    )
    refused_result = implementation.execute(context)
    _require(refused_result.failed, "Overwrite-disabled export was not refused")
    _require(target.read_bytes() == first_bytes, "Refused overwrite changed target bytes")
    _require(
        hashlib.sha256(target.read_bytes()).hexdigest() == first_hash,
        "Refused overwrite changed the target hash",
    )
    _assert_ui_state(expected_ui_state, label="refused overwrite")
    _require(not _temporary_glbs(target.parent), "Refused overwrite leaked a temporary GLB")

    race_target = target.with_name("publication concurrente.glb")
    race_target.unlink(missing_ok=True)
    context.metadata["export_output_path"] = str(race_target)
    race_plan = planning_module.build_export_plan(context)
    race_sentinel = b"concurrent writer sentinel"
    race_target.write_bytes(race_sentinel)
    try:
        blender_export_module.export_glb(race_plan)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Atomic no-clobber publication overwrote a concurrent file")
    _require(
        race_target.read_bytes() == race_sentinel,
        "Atomic no-clobber publication changed the concurrent file",
    )
    _assert_ui_state(expected_ui_state, label="concurrent publication refusal")
    _require(
        not _temporary_glbs(target.parent),
        "Concurrent publication refusal leaked a temporary GLB",
    )
    race_target.unlink()
    context.metadata["export_output_path"] = str(target)

    symlink_tested = False
    symlink_target = target.with_name("destination symbolique.glb")
    symlink_target.unlink(missing_ok=True)
    try:
        symlink_target.symlink_to(target.name)
    except OSError:
        pass
    else:
        symlink_tested = True
        context.metadata["export_output_path"] = str(symlink_target)
        context.metadata["export_overwrite_existing"] = True
        symlink_availability = implementation.availability(context)
        _require(
            not symlink_availability.available,
            "EXPORT accepted a symbolic-link destination",
        )
        _require(target.read_bytes() == first_bytes, "Symlink refusal changed its target")
        symlink_target.unlink()
        context.metadata["export_output_path"] = str(target)
        context.metadata["export_overwrite_existing"] = False

    context.metadata["export_overwrite_existing"] = True
    context.metadata["motion_source_path"] = str(target)
    source_collision_availability = implementation.availability(context)
    _require(
        not source_collision_availability.available,
        "EXPORT allowed its Motion source GLB to be used as destination",
    )
    source_collision_result = implementation.execute(context)
    _require(source_collision_result.failed, "Motion source overwrite was not refused")
    _require(target.read_bytes() == first_bytes,
             "Motion source overwrite refusal changed target bytes")
    _require(not _temporary_glbs(target.parent),
             "Motion source overwrite refusal leaked a temporary GLB")
    context.metadata.pop("motion_source_path")

    # A failed round-trip must never replace an existing valid destination,
    # even when the user explicitly enabled overwrite.
    fidelity_module = importlib.import_module(f"{package_name}.implementations.glb_export.fidelity")
    original_observe = fidelity_module.observe
    def corrupted_observation(*args, **kwargs):
        observed = original_observe(*args, **kwargs)
        observed["rest"] = tuple((x + 10.0, y, z) for x, y, z in observed["rest"])
        return observed
    # capture_expectation must stay honest; alter only the observations of the
    # imported temporary file by replacing the validator's observer after it.
    original_validate = fidelity_module.validate_roundtrip
    def corrupted_validation(*args, **kwargs):
        fidelity_module.observe = corrupted_observation
        try:
            return original_validate(*args, **kwargs)
        finally:
            fidelity_module.observe = original_observe
    fidelity_module.validate_roundtrip = corrupted_validation
    before_objects = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    try:
        refused_fidelity = implementation.execute(context)
    finally:
        fidelity_module.validate_roundtrip = original_validate
    _require(refused_fidelity.failed and "round-trip" in refused_fidelity.message,
             "Invalid round-trip was published")
    _require(target.read_bytes() == first_bytes, "Failed round-trip replaced the existing output")
    _require(set(bpy.data.objects) == before_objects and set(bpy.data.actions) == before_actions,
             "Failed round-trip leaked imported Blender data")
    _assert_ui_state(expected_ui_state, label="failed round-trip")
    _require(not _temporary_glbs(target.parent), "Failed round-trip leaked a temporary GLB")

    mesh_object.data.vertices[3].co.z += 0.375
    mesh_object.data.update()
    bpy.context.view_layer.update()
    context.metadata["export_overwrite_existing"] = True
    overwrite_availability = implementation.availability(context)
    _require(
        overwrite_availability.ready,
        f"Overwrite-enabled GLB export unavailable: {overwrite_availability.reason}",
    )
    overwrite_result = implementation.execute(context)
    overwrite_output, overwrite_bytes = _validate_static_export(
        overwrite_result,
        export_contracts=export_contracts,
        inspect_glb=manifest_module.inspect_glb,
        target=target,
        mesh_object=mesh_object,
    )
    _require(overwrite_bytes != first_bytes, "Overwrite did not replace the GLB bytes")
    _require(overwrite_output.sha256 != first_output.sha256,
             "Overwrite did not replace the GLB hash")
    _assert_ui_state(expected_ui_state, label="successful overwrite")
    _require(not _temporary_glbs(target.parent), "Successful overwrite leaked a temporary GLB")

    report = {
        "schema_version": 1,
        "path": str(target),
        "unicode_path": True,
        "initial_size_bytes": first_output.size_bytes,
        "initial_sha256": first_output.sha256,
        "overwrite_size_bytes": overwrite_output.size_bytes,
        "overwrite_sha256": overwrite_output.sha256,
        "mesh_count": overwrite_output.metrics["mesh_count"],
        "skin_count": overwrite_output.metrics["skin_count"],
        "animation_count": overwrite_output.metrics["animation_count"],
        "selection_restored": True,
        "active_object_restored": True,
        "frame_restored": True,
        "overwrite_refused_without_option": True,
        "concurrent_publication_refused": True,
        "symlink_destination_tested": symlink_tested,
        "motion_source_overwrite_refused": True,
        "glb_input_overwrite_refused": True,
        "typed_input_overwrite_refused": True,
        "failed_roundtrip_not_published": True,
        "roundtrip": context.metadata["glb_export_roundtrip"],
        "temporary_files_remaining": 0,
    }
    (output_root / "glb_export_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "GLB Export Blender smoke: PASS; "
        f"path={target.name}; bytes={overwrite_output.size_bytes}; "
        f"sha256={overwrite_output.sha256[:12]}; static mesh=1 skin=0 animation=0"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
