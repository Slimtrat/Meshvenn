"""Isolated, atomic Blender GLB export execution."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import bpy

from ...core.export_paths import protect_source_paths
from .manifest import GLBManifest, inspect_glb
from .planning import GLBExportPlan


@dataclass(frozen=True)
class _ObjectVisibility:
    object: Any
    hidden: bool
    hide_viewport: bool
    hide_render: bool
    hide_select: bool


@dataclass(frozen=True)
class _BlenderState:
    active_object: Any | None
    active_mode: str
    selected_objects: tuple[Any, ...]
    frame_current: int
    frame_subframe: float
    visibility: tuple[_ObjectVisibility, ...]


def _capture_state(plan: GLBExportPlan) -> _BlenderState:
    active = bpy.context.view_layer.objects.active
    return _BlenderState(
        active_object=active,
        active_mode=active.mode if active is not None else "OBJECT",
        selected_objects=tuple(bpy.context.selected_objects),
        frame_current=bpy.context.scene.frame_current,
        frame_subframe=bpy.context.scene.frame_subframe,
        visibility=tuple(
            _ObjectVisibility(
                object=obj,
                hidden=obj.hide_get(),
                hide_viewport=obj.hide_viewport,
                hide_render=obj.hide_render,
                hide_select=obj.hide_select,
            )
            for obj in plan.objects
        ),
    )


def _object_exists(obj: Any) -> bool:
    try:
        return bpy.data.objects.get(obj.name) is obj
    except ReferenceError:
        return False


def _prepare_selection(plan: GLBExportPlan) -> None:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    for obj in plan.objects:
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_select = False
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = plan.mesh_object
    bpy.context.view_layer.update()


def _restore_state(state: _BlenderState) -> None:
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    for item in state.visibility:
        if not _object_exists(item.object):
            continue
        item.object.hide_viewport = item.hide_viewport
        item.object.hide_render = item.hide_render
        item.object.hide_select = item.hide_select
        item.object.hide_set(item.hidden)
    for obj in state.selected_objects:
        if _object_exists(obj):
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
    if state.active_object is not None and _object_exists(state.active_object):
        bpy.context.view_layer.objects.active = state.active_object
        if state.active_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=state.active_mode)
            except RuntimeError:
                pass
    else:
        bpy.context.view_layer.objects.active = None
    bpy.context.scene.frame_set(state.frame_current, subframe=state.frame_subframe)
    bpy.context.view_layer.update()


@contextmanager
def _isolated_selection(plan: GLBExportPlan) -> Iterator[None]:
    state = _capture_state(plan)
    try:
        _prepare_selection(plan)
        yield
    finally:
        _restore_state(state)


@contextmanager
def _isolated_import(plan: GLBExportPlan) -> Iterator[None]:
    """Import probes with no original selected, then restore caller state.

    glTF creates its armature in Edit Mode without deselecting existing objects.
    Selecting the export rig here would enter multi-armature Edit Mode and
    recompose the authoritative rig's rest matrices even without editing bones.
    """
    state = _capture_state(plan)
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in tuple(bpy.context.selected_objects):
            obj.select_set(False)
        bpy.context.view_layer.objects.active = None
        yield
    finally:
        _restore_state(state)


@contextmanager
def _only_export_actions(actions: tuple[Any, ...]) -> Iterator[None]:
    if not actions:
        yield
        return

    import io_scene_gltf2

    filter_scene = bpy.data.scenes[0]
    had_filter = hasattr(bpy.types.Scene, "gltf_action_filter")
    saved_items: tuple[tuple[Any, bool], ...] = ()
    saved_active = 0
    if had_filter:
        saved_items = tuple(
            (item.action, bool(item.keep))
            for item in filter_scene.gltf_action_filter
        )
        saved_active = int(filter_scene.gltf_action_filter_active)
    else:
        bpy.types.Scene.gltf_action_filter = bpy.props.CollectionProperty(
            type=io_scene_gltf2.GLTF2_filter_action
        )
        bpy.types.Scene.gltf_action_filter_active = bpy.props.IntProperty()

    collection = filter_scene.gltf_action_filter
    collection.clear()
    wanted = {action.as_pointer() for action in actions}
    for action in bpy.data.actions:
        item = collection.add()
        item.action = action
        item.keep = action.as_pointer() in wanted

    try:
        yield
    finally:
        if hasattr(bpy.types.Scene, "gltf_action_filter"):
            filter_scene.gltf_action_filter.clear()
        if had_filter:
            for action, keep in saved_items:
                item = filter_scene.gltf_action_filter.add()
                item.action = action
                item.keep = keep
            filter_scene.gltf_action_filter_active = saved_active
        else:
            if hasattr(bpy.types.Scene, "gltf_action_filter"):
                del bpy.types.Scene.gltf_action_filter
            if hasattr(bpy.types.Scene, "gltf_action_filter_active"):
                del bpy.types.Scene.gltf_action_filter_active


def _validate_manifest(plan: GLBExportPlan, manifest: GLBManifest) -> None:
    if manifest.scene_count < 1:
        raise ValueError("Exported GLB contains no scene.")
    if manifest.mesh_count < 1:
        raise ValueError("Exported GLB contains no mesh.")
    if plan.rig is not None and manifest.skin_count < 1:
        raise ValueError("Exported GLB lost its rig skin.")
    if plan.motion is None and manifest.animation_names:
        raise ValueError("Static GLB export unexpectedly contains animations.")
    if plan.motion is not None and len(manifest.animation_names) != len(plan.actions):
        raise ValueError(
            "Exported GLB animation count does not match the Motion output: "
            f"expected {len(plan.actions)}, got {len(manifest.animation_names)}."
        )


def _publish_validated_glb(
    temporary_path: Path,
    destination: Path,
    *,
    overwrite_existing: bool,
) -> None:
    if overwrite_existing:
        os.replace(temporary_path, destination)
        return

    # Creating a hard link is an atomic no-clobber publication because source
    # and destination live in the same directory. It cannot replace a file (or
    # symlink) that appeared after planning, unlike os.replace(). The temporary
    # name is unlinked by the caller once the final artifact has been inspected.
    try:
        os.link(temporary_path, destination)
    except FileExistsError as exc:
        raise FileExistsError(
            "GLB export output appeared during export and was not overwritten: "
            f"{destination}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "The destination filesystem does not support atomic no-clobber GLB "
            f"publication: {destination}"
        ) from exc


def _export_prepared_glb(plan: GLBExportPlan, *, fidelity_report: dict | None = None,
                         modular_expected=None) -> GLBManifest:
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = plan.path.with_name(
        f".{plan.path.stem}.{uuid4().hex}.tmp.glb"
    )
    try:
        if plan.validate_roundtrip:
            from .fidelity import capture_expectation, validate_roundtrip
            expected = capture_expectation(plan)
        if plan.modular_spec is not None:
            from .modular_fidelity import capture_modular_expectation, validate_modular_roundtrip
            if modular_expected is None:
                modular_expected = capture_modular_expectation(plan, plan.modular_spec)
        with _isolated_selection(plan), _only_export_actions(plan.actions):
            options: dict[str, Any] = {
                # Blender's exporter appends a '/' to its directory, which is
                # invalid for Windows extended-length '\\?\' paths.
                "filepath": str(temporary_path).removeprefix("\\\\?\\")
                if os.name == "nt" and not str(temporary_path).startswith("\\\\?\\UNC\\")
                else str(temporary_path),
                "export_format": "GLB",
                "use_selection": True,
                "export_apply": False,
                "export_yup": True,
                "export_skins": plan.rig is not None,
                "export_animations": plan.motion is not None,
            }
            if plan.modular_spec is not None:
                options["export_extras"] = True
                options["export_rest_position_armature"] = True
                options["export_vertex_color"] = "ACTIVE"
                options["export_all_vertex_colors"] = True
                options["export_attributes"] = True
            if plan.motion is not None:
                options["export_animation_mode"] = (
                    "NLA_TRACKS" if plan.motion.implementation_id == "glb-source-motion-v1" else "ACTIONS"
                )
            result = bpy.ops.export_scene.gltf(**options)
            if "FINISHED" not in result:
                raise RuntimeError(f"Blender GLB export failed: {result}")

        if plan.modular_spec is not None:
            from .modular_normals import restore_modular_normals
            restore_modular_normals(temporary_path)
            from .modular_metadata import embed_modular_metadata
            embed_modular_metadata(temporary_path, plan.modular_spec)
        manifest = inspect_glb(temporary_path)
        _validate_manifest(plan, manifest)
        if plan.validate_roundtrip:
            with _isolated_import(plan):
                report = validate_roundtrip(plan, temporary_path, sha256=manifest.sha256, expected=expected)
            if fidelity_report is not None:
                fidelity_report.update(report)
        if plan.modular_spec is not None:
            with _isolated_import(plan):
                report = validate_modular_roundtrip(
                    plan, plan.modular_spec, temporary_path, modular_expected)
            if fidelity_report is not None:
                fidelity_report["modular_character"] = report
        protect_source_paths(plan.path, plan.source_paths)
        state = plan.prepared_modular_source
        if state is not None:
            state.commit()
        try:
            _publish_validated_glb(temporary_path, plan.path, overwrite_existing=plan.overwrite_existing)
        except Exception:
            if state is not None:
                state.rollback()
            raise
        # No new validation can fail after the atomic publication commit.
        return replace(manifest, path=plan.path)
    finally:
        temporary_path.unlink(missing_ok=True)


def export_glb(plan: GLBExportPlan, *, fidelity_report: dict | None = None) -> GLBManifest:
    if plan.modular_spec is None:
        return _export_prepared_glb(plan, fidelity_report=fidelity_report)
    from .modular_partition import prepare_modular_meshes
    from .modular_fidelity import capture_modular_expectation
    expected = capture_modular_expectation(plan, plan.modular_spec)
    with prepare_modular_meshes(plan, plan.modular_spec) as modular_plan:
        return _export_prepared_glb(modular_plan, fidelity_report=fidelity_report,
                                    modular_expected=expected)


__all__ = ("export_glb",)
