"""Prepare exact editable modular authority before publication, not inside export."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

import bpy

from ..core.modular_character.json_io import strict_json_loads
from ..core.modular_character.validation import text
from .glb_export import modular_source as source_api
from .glb_export.planning import build_export_plan


def catalogue_from_plan(plan):
    """Validate authoritative references and produce their exact declaration."""
    rig, motion, spec, scene = plan.rig, plan.motion, plan.modular_spec, bpy.context.scene
    if (plan.geometry.implementation_id != "native-visual-hull" or rig is None or spec is None
            or rig.implementation_id != spec.rig_id or spec.rig_id != "canonical-biped-v2"):
        raise ValueError("Prepared modular state requires native geometry and the declared Canonical Biped V2 rig.")
    armature = source_api._object(scene, rig.armature_object.name, "ARMATURE")
    if (armature is not rig.armature_object
            or source_api._property(armature, "meshvenn_rig_implementation") != rig.implementation_id):
        raise ValueError("Saved armature contradicts authored rig identity.")
    source_api._validate_semantics(rig.semantic_bones, armature)
    text(rig.binding_method, name="saved native binding_method")
    declared = spec.coordinates.normalization
    for obj in plan.mesh_objects:
        if source_api._object(scene, obj.name, "MESH") is not obj:
            raise ValueError("Authoritative source no longer matches its exact name.")
        if source_api._projection_space(obj) != plan.geometry.projection_space:
            raise ValueError("Saved projection provenance differs from Geometry.")
        normalization = source_api._normalization(obj)
        if (normalization != plan.geometry.normalization or normalization.normalized_height != declared.normalized_height
                or normalization.target_height != declared.target_height
                or not math.isclose(normalization.scale, declared.scale, rel_tol=1e-8, abs_tol=1e-12)):
            raise ValueError("Saved source normalization contradicts its explicit Geometry contract.")
        if (source_api._property(obj, "meshvenn_geometry_implementation") != plan.geometry.implementation_id
                or source_api._property(obj, "meshvenn_rig_implementation") != rig.implementation_id
                or strict_json_loads(source_api._property(obj, "meshvenn_rig_semantics")) != dict(rig.semantic_bones)):
            raise ValueError("Saved source native geometry/rig provenance is inconsistent.")
        source_api._validate_binding(obj, armature)
    value = {"schema_version": 1, "source_objects": [obj.name for obj in plan.mesh_objects],
        "rig": {"armature": armature.name, "implementation_id": rig.implementation_id,
                "semantic_bones": dict(rig.semantic_bones), "binding_method": rig.binding_method},
        "implementation_id": motion.implementation_id if motion else None,
        "source_bone_map": dict(motion.source_bone_map) if motion else {},
        "root_motion_mode": motion.root_motion_mode if motion else None,
        "clips": [{"name": clip.name, "action": clip.action.name, "frame_start": clip.frame_start,
                   "frame_end": clip.frame_end, "fps": clip.fps, "animated_roles": list(clip.animated_roles)}
                  for clip in motion.clips] if motion else []}
    source_api._motion(value, rig, scene)
    return value


def stage_authored_scene_catalogue(plan):
    """Authoring operation only: allocate an unreferenced owned Text."""
    payload = json.dumps(catalogue_from_plan(plan), indent=2, allow_nan=False)
    if len(payload.encode("utf-8")) > source_api.MAX_CATALOGUE_BYTES:
        raise ValueError("Saved authored-scene catalogue exceeds 16 MiB.")
    staged = bpy.data.texts.new(source_api.MOTION_CATALOGUE)
    try:
        staged.write(payload)
        staged.use_fake_user = True
        staged[source_api.CATALOGUE_OWNER] = 1
        staged["meshvenn_catalogue_committed"] = False
        return staged
    except Exception:
        bpy.data.texts.remove(staged)
        raise


def commit_authored_scene_catalogue(plan, staged):
    previous = [(obj, obj.get(source_api.CATALOGUE_REFERENCE)) for obj in plan.mesh_objects]
    try:
        for obj, _ in previous:
            obj[source_api.CATALOGUE_REFERENCE] = staged.name
        staged["meshvenn_catalogue_committed"] = True
    except Exception:
        for obj, value in previous:
            if value is None:
                obj.pop(source_api.CATALOGUE_REFERENCE, None)
            else:
                obj[source_api.CATALOGUE_REFERENCE] = value
        raise
    return staged.name


def discard_uncommitted_catalogue(staged):
    if staged is not None and not staged.get("meshvenn_catalogue_committed", False):
        bpy.data.texts.remove(staged)


@dataclass
class PreparedAuthoredSource:
    """Exact mesh/rig/spec/catalogue authority plus its owned pending commit."""
    plan: object
    catalogue: dict
    saved_text: object
    previous_references: tuple
    staged: bool
    committed: bool = False
    discarded: bool = False

    def validate(self, plan):
        if (self.discarded or plan.geometry is not self.plan.geometry or plan.rig is not self.plan.rig
                or plan.motion is not self.plan.motion or plan.mesh_objects != self.plan.mesh_objects
                or plan.modular_spec != self.plan.modular_spec):
            raise ValueError("Prepared authored state is stale; explicitly prepare the current source before export.")
        if catalogue_from_plan(plan) != self.catalogue:
            raise ValueError("Native catalogue changed after preparation; explicitly re-author it.")
        if (bpy.data.texts.get(self.saved_text.name) is not self.saved_text
                or len(self.saved_text.as_string().encode("utf-8")) > source_api.MAX_CATALOGUE_BYTES
                or strict_json_loads(self.saved_text.as_string()) != self.catalogue
                or self.saved_text.get(source_api.CATALOGUE_OWNER) != 1
                or self.saved_text.get("meshvenn_catalogue_committed") != (not self.staged or self.committed)):
            raise ValueError("Prepared source catalogue is missing or changed.")
        for obj, previous in self.previous_references:
            expected = self.saved_text.name if self.committed else previous
            if obj.get(source_api.CATALOGUE_REFERENCE) != expected:
                raise ValueError("Authoritative catalogue reference changed after preparation.")

    def commit(self):
        self.validate(self.plan)
        if self.staged and not self.committed:
            try:
                commit_authored_scene_catalogue(self.plan, self.saved_text)
            except Exception:
                self.rollback()
                raise
            self.committed = True
        return self.saved_text.name

    def rollback(self):
        if self.staged and not self.discarded:
            for obj, previous in self.previous_references:
                if previous is None:
                    obj.pop(source_api.CATALOGUE_REFERENCE, None)
                else:
                    obj[source_api.CATALOGUE_REFERENCE] = previous
            self.saved_text["meshvenn_catalogue_committed"] = False
            self.committed = False

    def discard(self):
        if self.staged and not self.committed and not self.discarded:
            # Opening another .blend can invalidate the old Blender IDs before
            # runtime cleanup. Do not delete a same-named Text from the new file.
            try:
                current = bpy.data.texts.get(self.saved_text.name)
            except ReferenceError:
                current = None
            if current is self.saved_text:
                discard_uncommitted_catalogue(self.saved_text)
            self.discarded = True


def prepare_authored_source(context, *, replace_existing=False):
    """Explicit authoring/load boundary; export may not call this function."""
    if type(replace_existing) is not bool:
        raise TypeError("replace_existing must be an explicit boolean.")
    previous_state = context.prepared_modular_source
    if previous_state is not None and not replace_existing:
        raise ValueError("Source is already prepared; explicitly replace preparation when re-authoring.")
    plan = build_export_plan(context)
    catalogue = catalogue_from_plan(plan)
    references = tuple((obj, obj.get(source_api.CATALOGUE_REFERENCE)) for obj in plan.mesh_objects)
    saved_text, staged = None, True
    if any(value is not None for _, value in references):
        existing = source_api._catalogue(plan.mesh_objects)
        if existing == catalogue:
            saved_text = bpy.data.texts[references[0][1]]
            staged = False
        elif not replace_existing:
            raise ValueError("Current outputs contradict the saved action catalogue; explicitly re-author instead of silently dropping clips.")
    if saved_text is None:
        saved_text = stage_authored_scene_catalogue(plan)
    state = PreparedAuthoredSource(plan, catalogue, saved_text, references, staged)
    try:
        state.validate(plan)
    except Exception:
        state.discard()
        raise
    if previous_state is not None:
        previous_state.discard()
    context.prepared_modular_source = state
    return state


def require_prepared_source(context, plan):
    state = context.prepared_modular_source
    if not isinstance(state, PreparedAuthoredSource):
        raise ValueError("Modular export requires prepared editable state; use Prepare Current Modular Source or Export Authored Source (No Rebuild).")
    state.validate(plan)
    return state
