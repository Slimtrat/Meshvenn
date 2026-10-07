"""Edit explicit whole-face region ownership; never classify from geometry or skin."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile

import bpy
import bmesh

from ...core.modular_character import ModularCharacterSpec, mesh_surface_sha256
from ...core.modular_character.json_io import strict_json_loads

ATTRIBUTE = "meshvenn_face_region"
STATE_KEY = "meshvenn_face_authoring"


def _surface(obj):
    if obj is None or obj.type != "MESH" or obj.library is not None or obj.data.library is not None:
        raise ValueError("Select a local authoritative mesh, not a preview or linked asset.")
    if obj.data.users != 1:
        raise ValueError("Face ownership editing requires a single-user source mesh.")
    if obj.get("meshvenn_source_mesh"):
        raise ValueError("Derived preview parts are not authoring authority.")
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bm.faces.index_update()
        points = [tuple(vertex.co) for vertex in bm.verts]
        faces = [tuple(vertex.index for vertex in face.verts) for face in bm.faces]
    elif obj.mode == "OBJECT":
        points = [tuple(vertex.co) for vertex in obj.data.vertices]
        faces = [tuple(face.vertices) for face in obj.data.polygons]
    else:
        raise ValueError("Use Object or Edit mode to author whole faces.")
    return mesh_surface_sha256(points, faces)


def _read(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Authoring JSON must be a regular file of at most 16 MiB.")
    return ModularCharacterSpec.from_dict(strict_json_loads(path.read_text("utf-8")))


def _state(obj):
    fingerprint = _surface(obj)
    state = strict_json_loads(obj.get(STATE_KEY, "{}"))
    if (not isinstance(state, dict) or type(state.get("schema_version")) is not int or state.get("schema_version") != 1 or state.get("source_object") != obj.name or
            state.get("surface_sha256") != fingerprint):
        raise ValueError("Missing or stale face authoring; load a hash-matching declaration explicitly.")
    ids = state.get("region_ids")
    if (not isinstance(ids, list) or not ids or not all(type(value) is str for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Invalid face-authoring region table.")
    attribute = obj.data.attributes.get(ATTRIBUTE)
    if attribute is None or attribute.domain != "FACE" or attribute.data_type != "INT":
        raise ValueError("Missing or incompatible face region attribute.")
    return state


def load_face_ownership(obj, spec, *, replace_existing=False):
    fingerprint = _surface(obj)
    if obj.mode != "OBJECT":
        raise ValueError("Load ownership in Object mode, then select faces in Edit mode.")
    if (obj.name not in spec.ownership or fingerprint != spec.ownership_source_sha256[obj.name]
            or len(spec.ownership[obj.name]) != len(obj.data.polygons)):
        raise ValueError("Ownership does not match the exact selected source surface.")
    existing = obj.data.attributes.get(ATTRIBUTE)
    if existing is not None:
        if not replace_existing:
            raise ValueError("Existing face edits are not overwritten; explicitly enable Replace Existing.")
        _state(obj)  # Never overwrite an unrelated attribute with the same name.
    ids = [region.id for region in spec.regions]
    codes = {region: index + 1 for index, region in enumerate(ids)}
    values = [codes[owner] for owner in spec.ownership[obj.name]]
    previous_state = obj.get(STATE_KEY)
    previous_values = [item.value for item in existing.data] if existing else None
    attribute = existing or obj.data.attributes.new(ATTRIBUTE, "INT", "FACE")
    try:
        attribute.data.foreach_set("value", values)
        obj[STATE_KEY] = json.dumps({"schema_version": 1, "source_object": obj.name,
                                    "surface_sha256": fingerprint, "region_ids": ids})
    except Exception:
        if existing is None:
            obj.data.attributes.remove(attribute)
        else:
            attribute.data.foreach_set("value", previous_values)
        if previous_state is None:
            obj.pop(STATE_KEY, None)
        else:
            obj[STATE_KEY] = previous_state
        raise


def assign_selected_faces(obj, region_id):
    state = _state(obj)
    if region_id not in state["region_ids"]:
        raise ValueError(f"Unknown declared region {region_id!r}.")
    code = state["region_ids"].index(region_id) + 1
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [face for face in bm.faces if face.select and not face.hide]
        layer = bm.faces.layers.int.get(ATTRIBUTE)
        if layer is None:
            raise ValueError("Edit mesh lost its loaded ownership layer.")
        if not selected:
            raise ValueError("Select at least one visible whole face.")
        for face in selected:
            face[layer] = code
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    else:
        selected = [face for face in obj.data.polygons if face.select and not face.hide]
        if not selected:
            raise ValueError("Select at least one visible whole face.")
        for face in selected:
            obj.data.attributes[ATTRIBUTE].data[face.index].value = code
    return len(selected)


def spec_from_face_ownership(obj, template):
    state = _state(obj)
    if state["region_ids"] != [region.id for region in template.regions]:
        raise ValueError("Region definitions changed; explicitly reload the new declaration.")
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.faces.layers.int.get(ATTRIBUTE)
        if layer is None:
            raise ValueError("Missing Edit-mode ownership layer.")
        values = [face[layer] for face in bm.faces]
    else:
        values = [item.value for item in obj.data.attributes[ATTRIBUTE].data]
    if any(type(value) is not int or not 1 <= value <= len(state["region_ids"]) for value in values):
        raise ValueError("Each source face must have exactly one declared region.")
    ownership = dict(template.ownership)
    if obj.name not in ownership or template.ownership_source_sha256[obj.name] != state["surface_sha256"]:
        raise ValueError("Template no longer matches the selected source.")
    ownership[obj.name] = tuple(state["region_ids"][value - 1] for value in values)
    result = replace(template, ownership=ownership)
    for name, expected in result.ownership_source_sha256.items():
        source = bpy.context.scene.objects.get(name)
        if source is None or _surface(source) != expected:
            raise ValueError("A declared source is missing or has stale geometry.")
    return result


def save_face_ownership(obj, template_path, output_path, *, overwrite=False):
    """Keep current socket/region declarations; atomically save only explicit edits."""
    template = _read(template_path)
    result = spec_from_face_ownership(obj, template)
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".json" or not destination.parent.is_dir():
        raise ValueError("Choose a .json file in an existing directory.")
    if destination.exists() and not overwrite:
        raise FileExistsError("Authoring JSON exists; explicitly enable Overwrite Existing JSON.")
    previous = destination.read_bytes() if destination.exists() else None
    payload = json.dumps(result.to_dict(), indent=2, allow_nan=False) + "\n"
    staged = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                         suffix=".json.tmp", delete=False) as stream:
            staged = Path(stream.name)
            stream.write(payload)
        if (destination.exists() and destination.read_bytes() != previous) or (previous is not None and not destination.exists()):
            raise ValueError("Authoring destination changed during save; retry after reviewing it.")
        if overwrite:
            os.replace(staged, destination)
        else:
            # Atomic no-clobber publication, including a competing creator
            # between the destination check and publication.
            os.link(staged, destination)
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
    return result
