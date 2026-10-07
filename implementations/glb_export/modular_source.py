"""Rehydrate an authored native scene without generating any replacement surface.

The JSON names the authoritative originals, never their derived preview copies.
The saved catalogue names the exact rig and Actions; missing provenance fails.
"""

from __future__ import annotations

import math
import json
import os
from pathlib import Path

import bpy

from ...core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from ...core.modular_character import ModularCharacterSpec
from ...core.modular_character.json_io import strict_json_loads
from ...core.modular_character.validation import fields, number, sequence, text, unique
from ...core.motion_contracts import MotionClipOutput, MotionOutput
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.rig_contracts import RigOutput
from .planning import build_export_plan


MOTION_CATALOGUE = "meshvenn-modular-motion.json"
MAX_CATALOGUE_BYTES = 16 * 1024 * 1024
CATALOGUE_REFERENCE = "meshvenn_modular_motion_catalogue"
CATALOGUE_OWNER = "meshvenn_modular_source_catalogue"


def stage_authored_scene_catalogue(plan):
    """Prepare portable source metadata before export; never overwrite user Texts.

    The staged Text is unreferenced until an entirely successful modular export.
    Failure cleanup removes it without changing any original source references.
    """
    if plan.geometry.implementation_id != "native-visual-hull":
        raise ValueError("Modular existing-source V1 requires saved native geometry provenance.")
    rig, motion = plan.rig, plan.motion
    spec, scene = plan.modular_spec, bpy.context.scene
    if rig is None or spec is None or rig.implementation_id != spec.rig_id or spec.rig_id != "canonical-biped-v2":
        raise ValueError("Authored modular source requires its declared Canonical Biped V2 rig.")
    armature = _object(scene, rig.armature_object.name, "ARMATURE")
    if (armature is not rig.armature_object
            or _property(armature, "meshvenn_rig_implementation") != rig.implementation_id):
        raise ValueError("Saved armature implementation contradicts its authored rig identity.")
    _validate_semantics(rig.semantic_bones, armature)
    text(rig.binding_method, name="saved native binding_method")
    declared = spec.coordinates.normalization
    for source in plan.mesh_objects:
        if _object(scene, source.name, "MESH") is not source:
            raise ValueError("Authored modular source no longer matches its exact saved name.")
        if _projection_space(source) != plan.geometry.projection_space:
            raise ValueError("Saved source projection provenance differs from the Geometry output.")
        normalization = _normalization(source)
        if (normalization["normalized_height"] != declared.normalized_height
                or normalization["target_height"] != declared.target_height
                or not math.isclose(normalization["normalization_scale"], declared.scale,
                                    rel_tol=1e-8, abs_tol=1e-12)):
            raise ValueError("Saved source normalization contradicts the certified modular declaration.")
        if (_property(source, "meshvenn_geometry_implementation") != plan.geometry.implementation_id
                or _property(source, "meshvenn_rig_implementation") != rig.implementation_id
                or strict_json_loads(_property(source, "meshvenn_rig_semantics")) != dict(rig.semantic_bones)):
            raise ValueError("Saved source native geometry/rig identity cannot be preserved for re-export.")
        _validate_binding(source, armature)
    value = {
        "schema_version": 1, "source_objects": [source.name for source in plan.mesh_objects],
        "rig": {"armature": rig.armature_object.name, "implementation_id": rig.implementation_id,
                "semantic_bones": dict(rig.semantic_bones), "binding_method": rig.binding_method},
        "implementation_id": motion.implementation_id if motion else None,
        "source_bone_map": dict(motion.source_bone_map) if motion else {},
        "root_motion_mode": motion.root_motion_mode if motion else None,
        "clips": [{"name": clip.name, "action": clip.action.name,
                   "frame_start": clip.frame_start, "frame_end": clip.frame_end, "fps": clip.fps,
                   "animated_roles": list(clip.animated_roles)} for clip in motion.clips] if motion else [],
    }
    # A successful product export must not persist a catalogue that fails its
    # own re-open route (including exact local Action names, timing and FPS).
    _motion(value, rig, scene)
    payload = json.dumps(value, indent=2, allow_nan=False)
    if len(payload.encode("utf-8")) > MAX_CATALOGUE_BYTES:
        raise ValueError("Saved authored-scene catalogue exceeds 16 MiB.")
    staged = bpy.data.texts.new(MOTION_CATALOGUE)
    try:
        staged.write(payload)
        # String references in source ID properties are not Blender ID users.
        staged.use_fake_user = True
        staged[CATALOGUE_OWNER] = 1
        staged["meshvenn_catalogue_committed"] = False
        return staged
    except Exception:
        bpy.data.texts.remove(staged)
        raise


def commit_authored_scene_catalogue(plan, staged):
    """Reference the successfully exported source catalogue, retaining prior Texts."""
    previous = [(source, source.get(CATALOGUE_REFERENCE)) for source in plan.mesh_objects]
    try:
        for source in plan.mesh_objects:
            source[CATALOGUE_REFERENCE] = staged.name
        staged["meshvenn_catalogue_committed"] = True
    except Exception:
        for source, value in previous:
            if value is None:
                source.pop(CATALOGUE_REFERENCE, None)
            else:
                source[CATALOGUE_REFERENCE] = value
        raise
    return staged.name


def discard_uncommitted_catalogue(staged):
    if staged is not None and not staged.get("meshvenn_catalogue_committed", False):
        bpy.data.texts.remove(staged)


def _property(obj, key):
    if key not in obj:
        raise ValueError(f"Authoritative source {obj.name!r} lacks saved provenance {key!r}.")
    return obj[key]


def _object(scene, name, kind):
    text(name, name=f"saved {kind} object name")
    obj = scene.objects.get(name)
    if obj is None or obj.type != kind or bpy.context.view_layer.objects.get(name) is not obj:
        raise ValueError(f"Saved authoritative {kind} object {name!r} is missing from the active scene.")
    if obj.library is not None or obj.data.library is not None:
        raise ValueError("Authored modular sources must be local editable objects, not linked libraries.")
    return obj


def _validate_semantics(semantics, armature):
    if (not isinstance(semantics, dict) or set(semantics.values()) != set(armature.data.bones.keys())
            or len(set(semantics.values())) != len(semantics)):
        raise ValueError("Saved semantic bone table must name every exact native joint once.")


def _validate_binding(source, armature):
    active = [modifier for modifier in source.modifiers if modifier.show_viewport or modifier.show_render]
    if len(active) != 1 or active[0].type != "ARMATURE" or active[0].object is not armature:
        raise ValueError("Authoritative source lost its exact native armature binding.")


def _normalization(source):
    enabled = _property(source, "bpt_normalize_height")
    if type(enabled) is not bool:
        raise TypeError("Saved normalization flag must be boolean.")
    return {"normalized_height": enabled,
            "target_height": number(_property(source, "bpt_target_height"), name="saved target_height",
                                    positive=True) if enabled else None,
            "normalization_scale": number(_property(source, "meshvenn_normalization_scale"),
                                          name="saved normalization_scale", positive=True)}


def _projection_space(source):
    return GeometryProjectionSpace(
        width=_property(source, "meshvenn_projection_width"),
        depth=_property(source, "meshvenn_projection_depth"),
        height=_property(source, "meshvenn_projection_height"),
        voxel_size=_property(source, "meshvenn_projection_voxel_size"),
        center_xy=_property(source, "meshvenn_projection_center_xy"),
        convention=_property(source, "meshvenn_projection_convention"))


def _catalogue(sources):
    references = {_property(source, CATALOGUE_REFERENCE) for source in sources}
    if len(references) != 1:
        raise ValueError("Authoritative source objects reference ambiguous rig/motion catalogues.")
    name = text(references.pop(), name="saved source catalogue reference")
    saved = bpy.data.texts.get(name)
    if (saved is None or saved.get(CATALOGUE_OWNER) != 1
            or saved.get("meshvenn_catalogue_committed") is not True):
        raise ValueError(f"Authored source lacks its committed native rig/motion catalogue {name!r}.")
    payload = saved.as_string()
    if len(payload.encode("utf-8")) > MAX_CATALOGUE_BYTES:
        raise ValueError("Saved rig/motion catalogue exceeds 16 MiB.")
    value = strict_json_loads(payload)
    fields(value, ("schema_version", "source_objects", "rig", "implementation_id", "source_bone_map", "root_motion_mode", "clips"),
           name="saved rig/motion catalogue")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported saved native source catalogue version.")
    names = sequence(value["source_objects"], name="saved source objects")
    unique(names, name="saved source object names")
    if set(names) != {source.name for source in sources}:
        raise ValueError("Saved rig/motion catalogue belongs to different authoritative source objects.")
    fields(value["rig"], ("armature", "implementation_id", "semantic_bones", "binding_method"),
           name="saved rig catalogue")
    return value


def _curves(action):
    try:
        return tuple(action.fcurves)
    except (AttributeError, RuntimeError, TypeError):
        return tuple(curve for layer in action.layers for strip in layer.strips
                     for bag in getattr(strip, "channelbags", ()) for curve in bag.fcurves)


def _motion(catalogue, rig, scene):
    declarations = sequence(catalogue["clips"], name="saved clips")
    if not declarations:
        # An explicitly empty catalogue is static; never discover unrelated Actions.
        if (catalogue["implementation_id"] is not None or catalogue["source_bone_map"] != {}
                or catalogue["root_motion_mode"] is not None):
            raise ValueError("Static catalogue must explicitly declare no motion implementation or roles.")
        return None
    if catalogue["implementation_id"] != "canonical-motion-retarget-v1":
        raise ValueError("Existing modular source requires its saved native motion implementation.")
    clips, action_names = [], []
    valid_paths = {bone.path_from_id(channel) for bone in rig.armature_object.pose.bones
                   for channel in ("rotation_quaternion", "rotation_euler", "rotation_axis_angle", "location", "scale")}
    scene_fps = float(scene.render.fps) / float(scene.render.fps_base)
    for declaration in declarations:
        fields(declaration, ("name", "action", "frame_start", "frame_end", "fps", "animated_roles"),
               name="saved motion clip")
        action_name = text(declaration["action"], name="saved action name")
        action = bpy.data.actions.get(action_name)
        if action is None or action.library is not None:
            raise ValueError(f"Declared native Action {action_name!r} is missing or not locally editable.")
        curves = _curves(action)
        if not curves or any(curve.data_path not in valid_paths for curve in curves):
            raise ValueError(f"Declared Action {action_name!r} does not target the saved native pose bones.")
        start = number(declaration["frame_start"], name="saved frame_start")
        end = number(declaration["frame_end"], name="saved frame_end")
        fps = number(declaration["fps"], name="saved clip fps", positive=True)
        if (not all(math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-5)
                    for expected, actual in zip((start, end), action.frame_range))
                or not math.isclose(fps, scene_fps, rel_tol=1e-8, abs_tol=1e-5)):
            raise ValueError(f"Declared Action {action_name!r} timing changed; re-author its saved catalogue.")
        clips.append(MotionClipOutput(declaration["name"], action, start, end, fps,
                                      sequence(declaration["animated_roles"], name="saved animated_roles")))
        action_names.append(action_name)
    unique(action_names, name="saved Action references")
    return MotionOutput(rig, rig.armature_object, catalogue["implementation_id"], tuple(clips),
                        catalogue["source_bone_map"], root_motion_mode=catalogue["root_motion_mode"],
                        metadata={"source": "saved-authored-scene", "catalogue": MOTION_CATALOGUE})


def _initial_static_catalogue(sources, binding_method):
    """Explicit migration for an old, unanimated native V2 source; never fallback.

    No catalogue/reference is written here. The exporter commits it only after
    the exact source has passed the ordinary modular publication gates.
    """
    if binding_method != "canonical-envelope-v2":
        raise ValueError("Static initialization requires the explicit canonical-envelope-v2 binding declaration.")
    if any(CATALOGUE_REFERENCE in source for source in sources):
        raise ValueError("A source already has a catalogue; use ordinary No Rebuild and repair invalid provenance explicitly.")
    armatures = []
    for source in sources:
        modifiers = [item for item in source.modifiers if item.show_viewport or item.show_render]
        if len(modifiers) != 1 or modifiers[0].type != "ARMATURE" or modifiers[0].object is None:
            raise ValueError("Static initialization requires exactly one native armature binding.")
        if _property(source, "meshvenn_rig_skinning_algorithm") != "regional-fitted-v2-leg-root-transfer":
            raise ValueError("This source's native binding is not qualified for static initialization.")
        armatures.append(modifiers[0].object)
    if len(set(armatures)) != 1:
        raise ValueError("Static source members must share the same exact native armature.")
    armature = armatures[0]
    animated_ids = set(sources) | {armature}
    for source in tuple(animated_ids):
        parent = source.parent
        while parent is not None:
            animated_ids.add(parent)
            parent = parent.parent
    animated_ids.update(obj.data for obj in tuple(animated_ids) if getattr(obj, "data", None) is not None)
    animated_ids.update(data.shape_keys for data in tuple(animated_ids) if getattr(data, "shape_keys", None) is not None)
    for source in animated_ids:
        animation = source.animation_data
        if animation is not None and (animation.action is not None or animation.drivers or
                                     any(track.strips for track in animation.nla_tracks)):
            raise ValueError("Static initialization refuses source/hierarchy Actions, NLA clips or drivers; author an exact motion catalogue instead.")
    return {"schema_version": 1, "source_objects": [source.name for source in sources],
            "rig": {"armature": armature.name, "implementation_id": "canonical-biped-v2",
                    "semantic_bones": strict_json_loads(_property(sources[0], "meshvenn_rig_semantics")),
                    "binding_method": binding_method},
            "implementation_id": None, "source_bone_map": {}, "root_motion_mode": None, "clips": []}


def context_from_authored_scene(scene, *, output_path=None, overwrite_existing=None,
                                initialize_static_source=False, binding_method=None):
    """Prepare only EXPORT from exact saved source references and native Actions.

    Does not create a mesh, fit a rig, retarget, alter pose, or execute INPUT or
    GEOMETRY. Editing source positions/topology requires re-authored ownership.
    """
    if scene is not bpy.context.scene:
        raise ValueError("Existing-source export requires the active Blender scene.")
    settings = getattr(scene, "bpt_settings", None)
    if settings is None or not settings.export_modular_character:
        raise ValueError("Existing-source export requires explicit Modular Character opt-in.")
    raw_manifest = settings.export_modular_manifest_path
    if not raw_manifest.strip():
        raise ValueError("Select the authoring JSON for the authoritative existing source.")
    manifest_path = Path(bpy.path.abspath(raw_manifest)).expanduser().resolve(strict=True)
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_CATALOGUE_BYTES:
        raise ValueError("Authoring JSON must be a regular file of at most 16 MiB.")
    spec = ModularCharacterSpec.from_dict(strict_json_loads(manifest_path.read_text("utf-8")))
    sources = tuple(_object(scene, name, "MESH") for name in spec.ownership)
    if type(initialize_static_source) is not bool:
        raise TypeError("initialize_static_source must be an explicit boolean.")
    if not initialize_static_source and binding_method is not None:
        raise ValueError("Binding declarations are only accepted during explicit static initialization.")
    catalogue = (_initial_static_catalogue(sources, binding_method) if initialize_static_source
                 else _catalogue(sources))
    declared_rig = catalogue["rig"]
    armature = _object(scene, declared_rig["armature"], "ARMATURE")
    if declared_rig["implementation_id"] != spec.rig_id or spec.rig_id != "canonical-biped-v2":
        raise ValueError("Saved source must retain the declared Canonical Biped V2 rig.")
    if _property(armature, "meshvenn_rig_implementation") != spec.rig_id:
        raise ValueError("Saved armature implementation contradicts its authored rig identity.")
    semantics = declared_rig["semantic_bones"]
    _validate_semantics(semantics, armature)
    text(declared_rig["binding_method"], name="saved native binding_method")
    normalization, projection_space = _normalization(sources[0]), _projection_space(sources[0])
    for source in sources:
        if (_property(source, "meshvenn_geometry_implementation") != "native-visual-hull"
                or _property(source, "meshvenn_rig_implementation") != spec.rig_id
                or strict_json_loads(_property(source, "meshvenn_rig_semantics")) != semantics
                or _projection_space(source) != projection_space or _normalization(source) != normalization):
            raise ValueError("Authoritative source provenance differs from its saved native geometry/rig.")
        _validate_binding(source, armature)
    geometry = GeometrySurfaceOutput(
        blender_object=sources[0], blender_objects=sources, source=spec,
        projection_space=projection_space, implementation_id="native-visual-hull",
        metadata={**normalization, "source": "saved-authored-scene"})
    rig = RigOutput(geometry, sources[0], armature, declared_rig["implementation_id"],
                    semantics, declared_rig["binding_method"])
    context = PipelineContext(scene=scene, settings=settings, metadata={
        "source": "saved-authored-scene-modular", "export_modular_character": True,
        "export_modular_manifest_path": str(manifest_path),
        "export_output_path": bpy.path.abspath(os.fspath(output_path) if output_path is not None else settings.export_output_path),
        "export_overwrite_existing": settings.export_overwrite_existing if overwrite_existing is None else overwrite_existing,
        "export_validate_roundtrip": True, "authored_source_blend_path": bpy.data.filepath,
        "authoritative_source_objects": tuple(source.name for source in sources),
    })
    context.set_output(PipelineStage.GEOMETRY, geometry)
    context.set_output(PipelineStage.RIG, rig)
    motion = _motion(catalogue, rig, scene)
    if motion is not None:
        context.set_output(PipelineStage.MOTION, motion)
    try:
        build_export_plan(context)
    except ValueError as exc:
        if "Stale ownership" in str(exc):
            raise ValueError("Authoritative source positions/topology changed; re-author ownership and its source fingerprint.") from exc
        raise
    return context


__all__ = ("context_from_authored_scene", "MOTION_CATALOGUE", "CATALOGUE_REFERENCE",
           "stage_authored_scene_catalogue", "commit_authored_scene_catalogue", "discard_uncommitted_catalogue")
