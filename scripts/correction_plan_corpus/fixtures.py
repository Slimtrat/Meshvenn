"""Independent author intent, original D2 rasters and predeclared D5 expectations.

No correction planner, provider, diagnostic engine or reconstruction is imported.
The shared PNG encoder is authoring code, not an algorithm being evaluated.
"""
from __future__ import annotations

from pathlib import Path

from scripts.appearance_diagnostic_corpus.authoring import canonical_json, png_rgba, sha256

from . import CORPUS_VERSION, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
PARENTS = {
    "appearance": ("tests/fixtures/diagnostics/appearance-v1/manifest.json",
                   "5fc81e9563bd6ee03ebc5b6f8b2f2eb003b8283aaa04a1f481788f6b4533d5e3"),
    "geometry": ("tests/fixtures/diagnostics/geometry-v1/manifest.json",
                 "aea6c48d9ffdfe1c5777291c4f0c82c945cb6fcd44e9a398fa9790ba9eb47a49"),
}

FULL_CAPABILITIES = {
    "profile_id": "corpus.capability_contract", "version": "1",
    "image_edit": True, "masks": True, "max_references": 8,
    "camera_constraints": True,
    "meaning": "Declared contract specimen only; no real provider was contacted or qualified.",
}

COMMON = ("originals_unchanged", "all_plans_bind_exact_sources_reports_policy_and_capabilities",
          "no_provider_execution", "no_general_semantic_or_human_qualification")


def appearance(case="local_colour_change", **options):
    return {"kind": "actual_D4", "parent_case_id": case, "raster_resolution": 32, **options}


def definition(identifier, split, source, intent, controls, *, mutation=None, capabilities=None):
    return {
        "case_id": identifier, "split": split, "source": source,
        "author_intent": intent, "capabilities": capabilities or FULL_CAPABILITIES,
        "prepare_mutation": mutation,
        "expected": {"controls": list(COMMON + tuple(controls))},
    }


def definitions():
    """Semantic controls are frozen independently of future DTO enum names."""
    masks = dict(FULL_CAPABILITIES, masks=False, profile_id="corpus.no_masks")
    single_ref = dict(FULL_CAPABILITIES, max_references=1, profile_id="corpus.single_reference")
    no_camera = dict(FULL_CAPABILITIES, camera_constraints=False, profile_id="corpus.no_camera_control")
    cases = [
        definition("targeted_visible_colour", "calibration", appearance(),
            {"allow_targeted_edit": True, "preserve_asymmetry": True},
            ("actual_local_D4_failure", "eligible_targeted_plan", "edit_has_bounded_region_and_accepted_reference",
             "explicit_D2_D3_D4_postconditions", "prepare_is_nonexecuting_package")),
        definition("intentional_asymmetry", "heldout", appearance("intentional_asymmetry"),
            {"allow_targeted_edit": False, "preserve_asymmetry": True},
            ("actual_named_D4_pass", "no_image_edit_without_supported_fault", "no_symmetry_correction")),
        definition("framing_preparation", "calibration", {"kind": "actual_D2", "recipe": "shifted"},
            {"fix_preparation_first": True},
            ("actual_alignment_proposal", "preparation_workflow", "no_image_regeneration_for_framing")),
        definition("mask_preparation", "heldout", {"kind": "actual_D2", "recipe": "empty_mask"},
            {"fix_preparation_first": True},
            ("actual_mask_failure", "mask_preparation_workflow", "no_image_regeneration_for_mask")),
        definition("missing_useful_view", "calibration", {"kind": "actual_D2", "recipe": "missing_side"},
            {"required_camera": {"azimuth_degrees": 90., "elevation_degrees": 0.}},
            ("actual_coverage_failure", "useful_view_workflow", "requested_direction_is_missing_observation")),
        definition("native_engine_failure", "heldout", {"kind": "actual_native_failure", "parent_case_id": "ambiguous_pair"},
            {"do_not_blame_images_for_engine_failure": True},
            ("actual_native_failure", "engine_diagnosis_workflow", "no_image_edit_for_engine_failure")),
        definition("ambiguous_geometry", "calibration", {"kind": "actual_D3", "parent_case_id": "ambiguous_pair"},
            {"no_automatic_fault_attribution": True},
            ("actual_ambiguous_geometry", "reference_choice_workflow", "no_unsupported_targeted_edit")),
        definition("canonical_geometry", "heldout", {"kind": "actual_D3", "parent_case_id": "canonical_resolves_pair"},
            {"canonical_mathematical_authority": True},
            ("actual_canonical_geometry_evidence", "canonical_evidence_retained", "no_unsupported_global_blame")),
        definition("unsupported_masks", "calibration", appearance(),
            {"allow_targeted_edit": True, "mask_is_required": True},
            ("eligible_edit_intent_preserved", "unsupported_masks_explicit", "no_silent_mask_drop", "not_prepared_for_provider"),
            capabilities=masks),
        definition("unsupported_multiple_references", "heldout", appearance(additional_reference={
            "parent_case_id":"healthy_reprojected", "view_id":"target", "role":"reference",
            "meaning":"Independent accepted original 45-degree view of the same authored body; preserve both references."}),
            {"allow_targeted_edit": True, "all_accepted_references_required": True},
            ("at_least_two_accepted_references", "unsupported_multiple_references_explicit", "no_silent_reference_drop",
             "not_prepared_for_provider"), capabilities=single_ref),
        definition("unsupported_camera_control", "heldout", appearance(),
            {"allow_targeted_edit": True, "verified_camera_constraint_required": True},
            ("unsupported_camera_explicit", "no_silent_camera_drop", "not_prepared_for_provider"), capabilities=no_camera),
        definition("stale_source", "calibration", appearance(), {"allow_targeted_edit": True},
            ("base_plan_preparable", "prepare_rejects_stale_source"), mutation={"kind": "source", "change": "target_revision_and_content"}),
        definition("stale_capabilities", "heldout", appearance(), {"allow_targeted_edit": True},
            ("base_plan_preparable", "prepare_rejects_stale_capabilities"), mutation={"kind": "capabilities", "change": "version"}),
        definition("stale_report", "calibration", appearance(), {"allow_targeted_edit": True},
            ("base_plan_preparable", "prepare_rejects_stale_report"), mutation={"kind": "report", "change": "finding_evidence_or_message"}),
        definition("stale_policy", "heldout", appearance(), {"allow_targeted_edit": True},
            ("base_plan_preparable", "prepare_rejects_stale_policy"), mutation={"kind": "policy", "change": "meaningful_configuration"}),
        definition("user_original_preserved", "heldout", appearance(origin="user"),
            {"allow_targeted_edit": True, "source_is_original_user_content": True,
             "provenance_limit": "Analytic stand-in for user-origin preservation; no real photograph or identity is qualified."},
            ("base_plan_preparable", "user_original_preserved", "candidate_lineage_is_derived_from_original")),
        definition("missing_semantic_evidence", "calibration", appearance("healthy_multicolour"),
            {"allow_targeted_edit": False},
            ("actual_semantic_unknown", "no_autoregeneration_for_missing_semantics")),
        definition("low_support_semantic_claim", "heldout", appearance("healthy_multicolour", semantic_mock="low_confidence_limited"),
            {"allow_targeted_edit": False},
            ("actual_local_semantic_mock_called", "actual_semantic_unknown", "no_autoregeneration_for_low_confidence")),
    ]
    return cases


def mask_pixel(x, y, size=64):
    u, v = x/(size-1), y/(size-1)
    return (.34 < u < .65 and .2 < v < .75) or (.65 < u < .76 and .52 < v < .65)


def build_corpus(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    assets = []
    def save(relative, data):
        path = destination/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        record = {"path": relative, "sha256": sha256(data), "bytes": len(data)}
        assets.append(record)
        return record
    size = 64
    for recipe in ("shifted", "empty_mask", "missing_side"):
        for view in ("target", "reference"):
            image, mask = bytearray(), bytearray()
            for y in range(size):
                for x in range(size):
                    sx, sy = (x-5, y+3) if recipe=="shifted" and view=="target" else (x, y)
                    inside = mask_pixel(sx, sy)
                    image.extend((52,101,187,255) if inside else (0,0,0,0))
                    selected = inside and not (recipe=="empty_mask" and view=="target")
                    mask.extend((255,255,255,255) if selected else (0,0,0,255))
            for kind, rgba in (("image", image), ("mask", mask)):
                save(f"assets/{recipe}/{view}-{kind}.png",
                     png_rgba(size, size, bytes(rgba), author_tag=f"original-d5-{recipe}-{view}-{kind}"))
    proof = {
        "schema_version": 1, "provenance": "Original analytic authoring; no planner, engine or provider output.",
        "coordinate_space": "bottom-left endpoint-grid pixels",
        "D2_shape": "(.34<u<.65 and .2<v<.75) or (.65<u<.76 and .52<v<.65)",
        "D2_shifted_target_pixels": [5,-3], "raster_size": size,
        "intentional_asymmetry": True, "canonical_evidence": "Mathematical author intent, not invented human review.",
        "D4_and_D3_sources": "Unmodified original independently frozen appearance-v1 and geometry-v1 fixtures.",
        "provider_qualification": False, "human_reviewed": False,
    }
    save("authoring-proof.json", canonical_json(proof))
    save("assets/invalid-native.bin", b"Original D5 bounded native-loader failure probe; this is deliberately not a shared library.\n")
    sources = []
    for relative in ("scripts/correction_plan_corpus/fixtures.py", "scripts/appearance_diagnostic_corpus/authoring.py"):
        raw = (ROOT/relative).read_bytes().replace(b"\r\n", b"\n")
        sources.append({"path":relative, "sha256_lf":sha256(raw)})
    manifest = {
        "schema_version": SCHEMA_VERSION, "corpus_version": CORPUS_VERSION,
        "expectations_frozen_before_D5_evaluation": True,
        "provenance": {"kind":"original_analytic_and_explicit_contract_specimens", "human_reviewed":False,
                       "real_provider_calls":0, "provider_fidelity_qualified":False, "generator_sources":sources},
        "parents": {key:{"path":value[0], "sha256":value[1]} for key,value in PARENTS.items()},
        "assets": assets, "cases": definitions(),
        "evaluation_plan": {"report_orders":["canonical","reverse"], "D4_sampling_size":32,
                            "D3_resolution":32, "D3_reprojection_size":64, "max_seconds_per_diagnostic":20.,
                            "native_optional_but_required_for_complete_qualification":True,
                            "edit_annotations":"When author intent allows a targeted edit, bind the measured finding to the original target-space authored ROI and its inline truth-region mask. The mask is an explicit author annotation, not inferred from diagnostic residuals.",
                            "semantic_mock":{"confidence":.2,"support":"limited","verdict":"changed",
                                             "qualification_evidence":None}},
        "limits": {"provider_execution":"not performed", "semantic_identity":"unqualified", "D6_D8":"unknown",
                   "initial_D7_and_issue_84":"open", "real_user_photographs":"not included"},
    }
    data = canonical_json(manifest)
    (destination/"manifest.json").write_bytes(data)
    return manifest, sha256(data)
