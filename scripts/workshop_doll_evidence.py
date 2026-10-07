"""Independent decoded-GLB comparison against the pinned full-body doll."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math


def _image_hashes(document, binary):
    result = []
    for image in document.get("images", []):
        if "uri" in image or "bufferView" not in image:
            raise ValueError("Workshop proof requires embedded, portable source textures.")
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        result.append(hashlib.sha256(binary[start:start + view["byteLength"]]).hexdigest())
    return result


def _records(document, binary, read_accessor):
    corners, triangles, binds = defaultdict(list), Counter(), {}
    images = _image_hashes(document, binary)
    materials = []
    for material in document.get("materials", []):
        pbr = dict(material.get("pbrMetallicRoughness", {}))
        texture = pbr.get("baseColorTexture")
        if texture is not None:
            declaration = document["textures"][texture["index"]]
            pbr["baseColorTexture"] = {"image_sha256": images[declaration["source"]],
                                       "texCoord": texture.get("texCoord", 0),
                                       "sampler": document.get("samplers", [])[declaration["sampler"]]}
        materials.append((pbr, material.get("alphaMode", "OPAQUE"), material.get("doubleSided", False)))
    count = 0
    for node in document["nodes"]:
        if "mesh" not in node:
            continue
        if "skin" not in node:
            raise ValueError("The delivered surface contains an unskinned mesh.")
        skin = document["skins"][node["skin"]]
        names = [document["nodes"][index]["name"] for index in skin["joints"]]
        matrices = read_accessor(document, binary, skin["inverseBindMatrices"])
        if len(set(names)) != 18 or len(names) != 18:
            raise ValueError("Workshop proof requires the same eighteen native joints.")
        for name, matrix in zip(names, matrices):
            if name in binds and binds[name] != tuple(matrix):
                raise ValueError("Regions do not share identical native inverse binds.")
            binds[name] = tuple(matrix)
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            if primitive.get("mode", 4) != 4:
                raise ValueError("Workshop proof requires triangles.")
            attributes = primitive["attributes"]
            if not {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"} <= set(attributes):
                raise ValueError("Workshop export lost source corner/skin attributes.")
            decoded = {name: read_accessor(document, binary, attributes[name]) for name in attributes}
            indices = [item[0] for item in read_accessor(document, binary, primitive["indices"])]
            keys = []
            for index in indices:
                position, uv = tuple(decoded["POSITION"][index]), tuple(decoded["TEXCOORD_0"][index])
                key = position + uv
                weights = {names[joint]: weight for joint, weight in zip(decoded["JOINTS_0"][index], decoded["WEIGHTS_0"][index]) if weight > 0}
                if not math.isclose(sum(weights.values()), 1, abs_tol=1e-6):
                    raise ValueError("Decoded source skin weights are not normalized.")
                corners[key].append((tuple(decoded["NORMAL"][index]), weights, materials[primitive["material"]]))
                keys.append(key)
            for offset in range(0, len(keys), 3):
                triangle = tuple(keys[offset:offset + 3])
                if len(triangle) != 3:
                    raise ValueError("Truncated source triangle.")
                # Allow vertex reindexing and cyclic ordering, NOT reversed winding
                # or a changed diagonal on any original nonplanar quad.
                triangles[min(triangle, triangle[1:] + triangle[:1], triangle[2:] + triangle[:2])] += 1
                count += 1
    return corners, triangles, binds, Counter(images), count


def compare_reference(reference, reference_binary, candidate, candidate_binary, read_accessor):
    expected, triangles, binds, images, count = _records(reference, reference_binary, read_accessor)
    actual, current_triangles, current_binds, current_images, current_count = _records(candidate, candidate_binary, read_accessor)
    if count != 14252 or current_count != count or triangles != current_triangles:
        raise ValueError("Partition changed exact source triangle corners, UVs, winding or tessellation.")
    if images != current_images:
        raise ValueError("Partition changed the embedded baked source image bytes.")
    if set(binds) != set(current_binds):
        raise ValueError("Partition changed native skin joint names.")
    bind_error = max(abs(a - b) for name in binds for a, b in zip(binds[name], current_binds[name]))
    if bind_error > 2e-4:
        raise ValueError("Partition changed the native inverse bind frame.")
    normal_error = weight_error = 0.0
    if set(expected) != set(actual):
        raise ValueError("Partition changed source position/UV corner identities.")
    for key, rows in expected.items():
        candidates = list(actual[key])
        if len(rows) != len(candidates):
            raise ValueError("Partition lost or duplicated a source corner.")
        for normal, weights, material in rows:
            matching = [index for index, (_, other_weights, other_material) in enumerate(candidates)
                        if set(weights) == set(other_weights) and material == other_material]
            if not matching:
                raise ValueError("Partition changed skin influences or source material semantics.")
            index = min(matching, key=lambda i: max(abs(a - b) for a, b in zip(normal, candidates[i][0])))
            other_normal, other_weights, _ = candidates.pop(index)
            normal_error = max(normal_error, max(abs(a - b) for a, b in zip(normal, other_normal)))
            weight_error = max(weight_error, max(abs(value - other_weights[name]) for name, value in weights.items()))
    if weight_error > 1e-6:
        raise ValueError(f"Partition changed normalized source weights ({weight_error}).")
    return {"passed": True, "triangle_count": count, "corner_count": count * 3,
            "positions_uv_winding_tessellation": "exact decoded source-corner multiset",
            "source_texture_bytes_identical": True, "reference_glb_normal_delta": normal_error,
            "normal_scope": "Diagnostic against the older whole-body export representation; exact Blender source corner normals are separately gated by modular fidelity at 2e-6, unchanged.",
            "max_weight_error": weight_error, "max_inverse_bind_error": bind_error,
            "scope": "Pinned full-body GLB comparison, separate from authoring-source and consumer gates."}


def compare_owned_variant(reference, reference_binary, candidate, candidate_binary, read_accessor):
    """Intentional source skin edit, never a relaxed unchanged-weight comparison.

    Exact new-source weights are independently gated by ordinary modular export.
    This checks the immutable baseline surface/material/bind and identifies the
    intentional skin differences without claiming old weights were preserved.
    """
    old, faces, binds, images, count = _records(reference, reference_binary, read_accessor)
    new, new_faces, new_binds, new_images, new_count = _records(candidate, candidate_binary, read_accessor)
    if count != 14252 or new_count != count or faces != new_faces or set(old) != set(new):
        raise ValueError("Authored skin edit changed original geometry/UV/winding/tessellation.")
    if images != new_images or binds != new_binds:
        raise ValueError("Authored skin edit changed embedded atlas or native inverse binds.")
    changed, normal_delta = 0, 0.0
    for key, rows in old.items():
        matches = list(new[key])
        if len(rows) != len(matches):
            raise ValueError("Authored skin edit lost or duplicated source corners.")
        for normal, weights, material in rows:
            candidates = [i for i, (_, _, other) in enumerate(matches) if other == material]
            if not candidates:
                raise ValueError("Authored skin edit changed material semantics.")
            i = min(candidates, key=lambda j: max(abs(a-b) for a,b in zip(normal, matches[j][0])))
            other_normal, edited, _ = matches.pop(i)
            if len(edited) > 4 or any(not math.isfinite(v) or v <= 0 for v in edited.values()):
                raise ValueError("Authored skin edit has invalid native influences.")
            changed += weights != edited
            normal_delta = max(normal_delta, max(abs(a-b) for a,b in zip(normal, other_normal)))
    if not changed:
        raise ValueError("Authored skin candidate contains no intentional weight edit.")
    return {"passed": True, "intentional_source_weight_edit": True, "changed_corner_count": changed,
            "triangle_count": count, "exact_surface_uv_materials_atlas_and_inverse_binds_preserved": True,
            "reference_normal_delta_diagnostic": normal_delta,
            "scope": "Before/after source weight edit. New-source skin fidelity is separately gated by export; old weights are intentionally not retained."}


def compare_head_variant(reference, reference_binary, candidate, candidate_binary, read_accessor, envelope):
    """Separate intentional edit proof; NEVER a relaxation of compare_reference.

    Preserve exact surface/material/image/bind authority. Only the explicitly
    observed head transition may change weights, according to convex transfer.
    Below that transition, skin weights must remain exactly the decoded baseline.
    """
    from core.rig_head_envelope import HeadEnvelope, isolate_head_weights
    profile = HeadEnvelope(envelope["start_z"], envelope["end_z"], envelope["neck_z"],
                           envelope["contrast"], envelope["closed_section_count"])
    old, faces, binds, images, count = _records(reference, reference_binary, read_accessor)
    new, new_faces, new_binds, new_images, new_count = _records(candidate, candidate_binary, read_accessor)
    if count != 14252 or count != new_count or faces != new_faces or set(old) != set(new):
        raise ValueError("Head variant changed exact source geometry, UVs, winding or tessellation.")
    if images != new_images or binds != new_binds:
        raise ValueError("Head variant changed embedded atlas bytes or native inverse binds.")
    changed, normal_delta = 0, 0.0
    for key, rows in old.items():
        candidates = list(new[key])
        if len(rows) != len(candidates):
            raise ValueError("Head variant duplicated or lost surface corners.")
        for normal, weights, material in rows:
            matching = [i for i, (_, _, other_material) in enumerate(candidates) if material == other_material]
            if not matching:
                raise ValueError("Head variant changed source material semantics.")
            i = min(matching, key=lambda j: max(abs(a-b) for a,b in zip(normal, candidates[j][0])))
            other_normal, actual, _ = candidates.pop(i)
            # glTF Y is native Blender Z for this pinned source's mesh accessor.
            expected = isolate_head_weights(weights, key[1], profile)
            if (set(expected) != set(actual) or len(actual) > 4
                    or max(abs(expected[n]-actual[n]) for n in expected) > 1e-6):
                raise ValueError("Head variant changed weights outside the declared head transfer.")
            if key[1] <= profile.start_z and weights != actual:
                raise ValueError("Head variant changed lower-body source weights.")
            changed += weights != actual
            normal_delta = max(normal_delta, max(abs(a-b) for a,b in zip(normal, other_normal)))
    if not changed:
        raise ValueError("Head variant did not change skin weights.")
    return {"passed": True, "intentional_head_weights_edit": True, "changed_corner_count": changed,
            "triangle_count": count, "source_surface_uv_materials_atlas_and_inverse_binds_preserved": True,
            "below_neck_weights_exact": True, "reference_glb_normal_delta_diagnostic": normal_delta,
            "scope": "New selected-source weights; NOT unchanged baseline weight fidelity or artistic qualification."}
