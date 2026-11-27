"""Reopen/re-export a cloth bundle and independently test public GLB LOD fidelity.

No private consumer capture is required by this CI gate. Exact consumer replay
is an additional, explicitly external gate; it is never replaced by these probes.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender import source
from meshvenn_humanoid.blender.evaluation import make_regions, measure
from meshvenn_humanoid.blender.probes import evaluated_positions, rotated_bone
from meshvenn_humanoid.models import LIMITS
from scripts.author_stytch_cloth import api
from scripts.author_stytch_doll import source_snapshot
from scripts.cloth_lod import (
    POLICY,
    REFERENCE_SHA256,
    sampled_distance,
    surface,
    write_json,
)


def material_signature(path):
    reader = api("implementations.glb_export.modular_gltf")
    document, binary = reader.read_glb(path)
    images = []
    for image in document["images"]:
        if "uri" in image:
            raise ValueError("Cloth textures must be embedded")
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        images.append(
            hashlib.sha256(binary[start : start + view["byteLength"]]).hexdigest()
        )

    def canonical(value):
        if isinstance(value, list):
            return [canonical(v) for v in value]
        if not isinstance(value, dict):
            return value
        return {
            k: (
                texture(v)
                if k.endswith("Texture") and isinstance(v, dict) and "index" in v
                else canonical(v)
            )
            for k, v in value.items()
        }

    def texture(info):
        result = deepcopy(info)
        declaration = document["textures"][result.pop("index")]
        result["image_sha256"] = images[declaration["source"]]
        result["sampler"] = (
            document["samplers"][declaration["sampler"]]
            if "sampler" in declaration
            else None
        )
        return result

    # Extras/name are authoring provenance/labels, not shader inputs. The new
    # modular export retains cloth provenance absent from the older full-body
    # GLB. Compare every actual PBR field, texture binding and sampler instead.
    materials = [
        {k: v for k, v in material.items() if k not in ("extras", "name")}
        for material in document["materials"]
    ]
    return {"images": sorted(images), "materials": canonical(materials)}


def glb_surfaces(path):
    """Combine imported copies for measurement only; never edit the artifact."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path), disable_bone_shape=True)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(rigs) != 1 or not meshes:
        raise ValueError("Expected one native rig and a nonempty surface")
    rig = rigs[0]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    mesh = bpy.context.view_layer.objects.active
    points, triangles = surface(mesh)
    regions = make_regions(mesh, rig, points)
    values, evidence = measure(mesh, rig, regions)
    surfaces = {"rest": (points, triangles)}
    for side in ("L", "R"):
        for joint, degrees, axis in (
            ("forearm", 45, (0, 1, 0)),
            ("forearm", 90, (0, 1, 0)),
            ("upper_arm", 45, (0, 1, 0)),
            ("upper_arm", 70, (0, 1, 0)),
            ("hand", 45, (0, 1, 0)),
            ("thigh", 45, (1, 0, 0)),
            ("shin", 90, (1, 0, 0)),
            ("foot", 30, (1, 0, 0)),
        ):
            with rotated_bone(
                rig,
                joint + "." + side,
                degrees if side == "L" else -degrees,
                axis,
                world_space=True,
            ):
                surfaces[f"native-{joint}-{side}-{degrees}"] = (
                    evaluated_positions(mesh),
                    triangles,
                )
    return surfaces, values, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    fixture = args.fixture.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((fixture / "manifest.json").read_text("utf-8"))
    asset, blend = fixture / "character.glb", fixture / "source.blend"
    reference = ROOT / "example/v2/generated/StytchDummyCloth/character.glb"
    if (
        source.digest(asset) != manifest["sha256"]
        or source.digest(blend) != manifest["editable_source_sha256"]
        or source.digest(reference) != REFERENCE_SHA256
    ):
        raise ValueError("Immutable bundle/reference hash mismatch")
    if (
        manifest["selected"]
        or manifest["visual_acceptance"]
        or manifest["consumer_admission"]
    ):
        raise ValueError("This fixture must remain a non-admitted producer candidate")
    budget = {
        "max_sampled_surface_error_m": POLICY["max_sampled_surface_error_m"],
        "p99_sampled_surface_error_m": POLICY["p99_sampled_surface_error_m"],
        "native_limits": LIMITS,
        "native_probe_count": 16,
        "scope": "Public GLB import fidelity and native probes, not an actual Stytch replay",
    }
    write_json(output / "budget.json", budget)
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False, use_scripts=False)
        mesh = bpy.data.objects["MeshvennScan"]
        rig = bpy.data.objects["MeshvennCanonicalRig"]
        before = source_snapshot(mesh, rig)
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_character = True
        settings.export_modular_manifest_path = str(fixture / "authoring.json")
        settings.export_output_path = str(output / "reexport.glb")
        settings.export_overwrite_existing = False
        result = bpy.ops.bpt.export_existing_modular_source()
        if result != {"FINISHED"} or source_snapshot(mesh, rig) != before:
            raise ValueError("No Rebuild failed or changed exact source authority")
    finally:
        package.unregister()
    appearance = material_signature(asset)
    if appearance != material_signature(reference) or appearance != material_signature(
        output / "reexport.glb"
    ):
        raise ValueError(
            "Source/LOD/re-export changed an embedded map or PBR material semantic"
        )
    expected, _, _ = glb_surfaces(reference)
    actual, values, evidence = glb_surfaces(asset)
    failures = {
        k: v
        for k, v in values.items()
        if (v > LIMITS[k][1] if LIMITS[k][0] == "max" else v < LIMITS[k][1])
    }
    report = {
        "schema_version": 1,
        "asset_sha256": manifest["sha256"],
        "source_sha256": manifest["editable_source_sha256"],
        "budget": budget,
        "native_profile": values,
        "native_failures": failures,
        "native_evidence": evidence,
        "appearance": appearance,
        "source_authority_unchanged": True,
        "no_rebuild_passed": True,
        "poses": [],
        "passed": False,
        "consumer_replay_performed": False,
        "visual_acceptance": False,
    }
    for label in expected:
        error = sampled_distance(expected[label], actual[label])
        passed = (
            error["max"] <= budget["max_sampled_surface_error_m"]
            and error["p99"] <= budget["p99_sampled_surface_error_m"]
        )
        report["poses"].append({"pose": label, "error_m": error, "passed": passed})
        write_json(output / "qualification.json", report)
    report["passed"] = not failures and all(r["passed"] for r in report["poses"])
    if (
        source.digest(asset) != manifest["sha256"]
        or source.digest(blend) != manifest["editable_source_sha256"]
    ):
        raise ValueError("Qualification changed the frozen bundle")
    write_json(output / "qualification.json", report)
    if not report["passed"]:
        raise ValueError("Cloth modular qualification failed; evidence retained")
    print(
        "Cloth candidate PASS: exact source No Rebuild, three maps/PBR, native profile and 17 public GLB states; consumer admission remains separate"
    )


if __name__ == "__main__":
    main()
