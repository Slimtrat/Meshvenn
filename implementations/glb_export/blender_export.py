"""Isolated, atomic Blender GLB export execution."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import bpy

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
    visibility: tuple[_ObjectVisibility, ...]


def _capture_state(plan: GLBExportPlan) -> _BlenderState:
    active = bpy.context.view_layer.objects.active
    return _BlenderState(
        active_object=active,
        active_mode=active.mode if active is not None else "OBJECT",
        selected_objects=tuple(bpy.context.selected_objects),
        frame_current=bpy.context.scene.frame_current,
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
    bpy.context.scene.frame_set(state.frame_current)
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
        raise ValueError("Exported GLB lost the canonical skin.")
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


def export_glb(plan: GLBExportPlan) -> GLBManifest:
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = plan.path.with_name(
        f".{plan.path.stem}.{uuid4().hex}.tmp.glb"
    )
    try:
        with _isolated_selection(plan), _only_export_actions(plan.actions):
            options: dict[str, Any] = {
                "filepath": str(temporary_path),
                "export_format": "GLB",
                "use_selection": True,
                "export_apply": False,
                "export_yup": True,
                "export_skins": plan.rig is not None,
                "export_animations": plan.motion is not None,
            }
            if plan.motion is not None:
                options["export_animation_mode"] = "ACTIONS"
            result = bpy.ops.export_scene.gltf(**options)
            if "FINISHED" not in result:
                raise RuntimeError(f"Blender GLB export failed: {result}")

        manifest = inspect_glb(temporary_path)
        _validate_manifest(plan, manifest)
        _publish_validated_glb(
            temporary_path,
            plan.path,
            overwrite_existing=plan.overwrite_existing,
        )
        return inspect_glb(plan.path)
    finally:
        temporary_path.unlink(missing_ok=True)


__all__ = ("export_glb",)
