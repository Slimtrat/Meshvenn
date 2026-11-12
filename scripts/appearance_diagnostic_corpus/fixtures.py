"""Frozen authoring specifications and independent synthetic appearance truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import CORPUS_VERSION, SCHEMA_VERSION
from .authoring import canonical_json, png_rgba, render, scene, sha256
from .preview import case_panel

RASTERS = (32,64)
GENERATOR = "original-linear-ray-triangle-albedo/1"


@dataclass(frozen=True)
class Case:
    case_id: str
    split: str
    outcome: str
    injection: str = "none"
    reference_azimuth: int = 0
    target_azimuth: int = 0
    mesh_kind: str = "body"
    photometry: str = "albedo-srgb"
    gain: float = 1.
    lineage: str = "independent-authored"
    service: str = "not-configured"
    scope: str = "numeric-analytic"
    region: str = "shared_patch"


# These are authoring expectations, not conclusions read from a D4 evaluator.
# Every definition and expected outcome is frozen before any diagnostic run.
CASES = (
    Case("healthy_multicolour", "calibration", "pass"),
    Case("local_colour_change", "calibration", "fail", "local_colour", region="colour_patch"),
    Case("removed_visible_motif", "heldout", "fail", "removed_motif", region="identity_motif"),
    Case("intentional_asymmetry", "heldout", "pass", "intentional_asymmetry"),
    Case("occluded_in_reference", "calibration", "unknown", "occlusion_patch", 0,45,"occluder", region="occluded_patch"),
    Case("occluded_in_target", "heldout", "unknown", "occlusion_patch",45,0,"occluder", region="occluded_patch"),
    Case("never_observed_region", "heldout", "unknown", region="back_unobserved"),
    Case("unverified_camera", "calibration", "unknown", "unverified_camera"),
    Case("ambiguous_surface", "heldout", "unknown", mesh_kind="ambiguous"),
    Case("controlled_neutral_gain", "calibration", "pass", photometry="controlled-neutral-gain-srgb", gain=.65),
    Case("uncontrolled_lighting", "heldout", "unknown", photometry="uncontrolled-lit-srgb", gain=.65),
    Case("reference_from_target", "calibration", "unknown", "local_colour", lineage="reference-derived-from-target", region="colour_patch"),
    Case("circular_reference", "heldout", "unknown", "local_colour", lineage="circular", region="colour_patch"),
    Case("canonical_ancestor_allowed", "heldout", "fail", "local_colour", lineage="target-descends-from-reference", region="colour_patch"),
    Case("stale_source", "calibration", "unknown", "stale_source"),
    Case("upstream_geometry_fail", "heldout", "pass_or_unknown", "upstream_geometry_fail", scope="upstream-contract"),
    Case("healthy_reprojected", "heldout", "pass", reference_azimuth=0,target_azimuth=45),
    Case("service_unavailable", "calibration", "pass", service="unavailable", scope="adapter-only"),
    Case("service_malformed", "calibration", "pass", service="malformed", scope="adapter-only"),
    Case("service_conflicting", "heldout", "pass", service="conflicting", scope="adapter-only"),
    Case("service_low_evidence", "heldout", "pass", service="low-evidence", scope="adapter-only"),
    Case("service_supported_mock", "calibration", "pass", service="supported-mock", scope="adapter-only"),
)


# Rectangles live on the authored front/back planes. They are mathematical
# region definitions; they are not inferred from a diagnostic's output.
REGIONS = {
    "shared_patch": {"label": "shared_patch", "surface_label": "body_front", "x": [.08,.60], "z": [-.56,-.16], "y": -.35},
    "colour_patch": {"label": "colour_patch", "surface_label": "body_front", "x": [-.58,-.22], "z": [-.48,-.14], "y": -.35},
    "identity_motif": {"label": "identity_motif", "surface_label": "body_front", "x": [.1152,.5184], "z": [.13,.52], "y": -.35},
    "occluded_patch": {"label": "occluded_patch", "surface_label": "body_front", "x": [.18,.38], "z": [.06,.34], "y": -.35},
    "back_unobserved": {"label": "back_unobserved", "surface_label": "body_back", "x": [-.3,.3], "z": [-.2,.3], "y": .35},
}


def inside_region(hit, region):
    if hit is None or hit["surface_label"] != region["surface_label"]:
        return False
    x,_y,z = hit["position"]
    return region["x"][0]-1e-9 <= x <= region["x"][1]+1e-9 and region["z"][0]-1e-9 <= z <= region["z"][1]+1e-9


def projected_bounds(region, azimuth):
    # Independent explicit native elev=0 camera equation; no tested helper.
    import math
    a = math.radians(azimuth)
    ca,sa = math.cos(a),math.sin(a)
    h = abs(ca)+abs(sa)
    us = [((x*ca+region["y"]*sa)/h+1)/2 for x in region["x"]]
    return [min(us), (region["z"][0]+1)/2, max(us), (region["z"][1]+1)/2]


def expected(case):
    controls = ["original_input_integrity_checked", "semantic_quality_unknown_without_real_approved_analyzer", "no_automatic_correction"]
    if case.outcome == "pass":
        controls += ["observed_named_region_numeric_pass"]
    elif case.outcome == "fail":
        controls += ["observed_named_region_numeric_fail", "localized_failure_overlaps_authored_region", "unaffected_shared_region_numeric_pass"]
    else:
        controls += ["no_unsupported_colour_fault_attribution"]
    if case.injection in ("occlusion_patch",) or case.region == "back_unobserved":
        controls += ["unavailable_named_region_unknown", "unaffected_shared_region_numeric_pass"]
    if case.injection == "unverified_camera":
        controls += ["unverified_camera_unknown"]
    if case.mesh_kind == "ambiguous":
        controls += ["ambiguous_surface_correspondence_unknown"]
    if case.photometry == "controlled-neutral-gain-srgb":
        controls += ["declared_scalar_gain_used", "raw_photometric_difference_retained"]
    if case.photometry == "uncontrolled-lit-srgb":
        controls += ["true_colour_unknown_under_uncontrolled_lighting", "raw_photometric_difference_retained"]
    if case.lineage in ("reference-derived-from-target", "circular"):
        controls += ["circular_or_target_derived_reference_rejected", "reference_cannot_self_validate_target"]
    if case.lineage == "target-descends-from-reference":
        controls += ["accepted_design_ancestor_reference_usable"]
    if case.injection == "stale_source":
        controls += ["stale_content_reference_detected", "input_failure_not_erased"]
    if case.injection == "upstream_geometry_fail":
        controls += ["same_upstream_geometry_fail_preserved", "overall_verification_cannot_pass"]
    if case.scope == "adapter-only":
        controls += ["actual_numeric_engine_still_evaluated", "semantic_mock_adapter_scope_only", "semantic_quality_not_qualified"]
        controls += [{"unavailable":"service_unavailable_unknown", "malformed":"malformed_response_rejected",
                      "conflicting":"conflicting_claims_preserved_and_unknown", "low-evidence":"unsupported_claim_unknown",
                      "supported-mock":"valid_mock_contract_preserved"}[case.service]]
    return {"named_region_status": ["pass","unknown"] if case.outcome == "pass_or_unknown" else [case.outcome],
            "region_label": case.region, "required_controls": controls,
            "semantic_identity_status": "unknown", "claim_scope": case.scope,
            "threshold_fitting_allowed": False}


def build_corpus(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    meshes = {"body":scene(), "occluder":scene(occluder=True), "ambiguous":scene(ambiguous=True)}
    mesh_records = {}
    for name, mesh in meshes.items():
        path = f"sources/mesh-{name}.json"
        data = canonical_json(mesh)
        (destination/path).parent.mkdir(parents=True, exist_ok=True)
        (destination/path).write_bytes(data)
        mesh_records[name] = {"path":path,"sha256":sha256(data),"vertex_count":len(mesh["vertices"]),"triangle_count":len(mesh["triangles"])}
    cache, cases, panel = {}, [], []
    def get_render(kind, angle, size, variant, injection, gain):
        key = (kind,angle,size,variant,injection,gain)
        if key not in cache:
            cache[key] = render(meshes[kind],angle,size,variant=variant,injection=injection,gain=gain)
        return cache[key]
    for spec in CASES:
        variant = "intentional_asymmetry" if spec.injection == "intentional_asymmetry" else "base"
        target_injection = spec.injection if spec.injection in ("local_colour","removed_motif","occlusion_patch") else "none"
        reference_injection = target_injection if spec.lineage in ("reference-derived-from-target","circular") else "none"
        region = REGIONS[spec.region]
        variants = []
        for size in RASTERS:
            images = {}
            pixels_by_role = {}
            for role, angle, injection, gain in (("reference",spec.reference_azimuth,reference_injection,1.),
                                                  ("target",spec.target_azimuth,target_injection,spec.gain)):
                rgba,hits = get_render(spec.mesh_kind,angle,size,variant,injection,gain)
                pixels_by_role[role] = rgba
                path = f"assets/{spec.case_id}/{size}/{role}.png"
                data = png_rgba(size,size,rgba,author_tag=f"{CORPUS_VERSION}/{spec.case_id}/{size}/{role}")
                mask = bytes(channel for hit in hits for channel in ((255,255,255,255) if inside_region(hit,region) else (0,0,0,0)))
                mask_data = png_rgba(size,size,mask,author_tag=f"{CORPUS_VERSION}/{spec.case_id}/{size}/{role}-truth-region")
                mask_path = f"assets/{spec.case_id}/{size}/{role}-truth-region.png"
                for relative, content in ((path,data),(mask_path,mask_data)):
                    (destination/relative).parent.mkdir(parents=True,exist_ok=True)
                    (destination/relative).write_bytes(content)
                images[role] = {"path":path,"sha256":sha256(data),"width":size,"height":size,"media_type":"image/png",
                    "camera":{"projection":"orthographic","azimuth_degrees":angle,"elevation_degrees":0,"flip_x":False,
                              "verified":not(role=="target" and spec.injection=="unverified_camera")},
                    "photometry":{"mode":spec.photometry if role=="target" else "albedo-srgb","colour_space":"srgb",
                                  "declared_linear_gain":gain if role=="target" and spec.photometry=="controlled-neutral-gain-srgb" else None},
                    "foreground_pixels":sum(hit is not None for hit in hits),
                    "visible_named_region_pixels":sum(inside_region(hit,region) for hit in hits),
                    "region_projected_bounds":projected_bounds(region,angle),
                    "truth_region_mask":{"path":mask_path,"sha256":sha256(mask_data)},
                    "lineage":{"origin":"rendered","derived_from":[]}}
            if spec.lineage == "target-descends-from-reference":
                images["target"]["lineage"] = {"origin":"derived","derived_from":[images["reference"]["sha256"]]}
            if spec.lineage in ("reference-derived-from-target","circular"):
                images["reference"]["lineage"] = {"origin":"derived","derived_from":[images["target"]["sha256"]]}
            if spec.lineage == "circular":
                images["target"]["lineage"] = {"origin":"derived","derived_from":[images["reference"]["sha256"]]}
            for role, record in images.items():
                record["declared_content_sha256"] = "0"*64 if role=="target" and spec.injection=="stale_source" else record["sha256"]
            variants.append({"raster_resolution":size,"views":images})
            if size == 64:
                label = "NUM PASS - MOCK ONLY" if spec.scope == "adapter-only" else "EXPECT " + spec.outcome.replace("_or_", "/")
                panel.append((spec.case_id, f"R{spec.reference_azimuth} T{spec.target_azimuth} {label}",pixels_by_role["reference"],pixels_by_role["target"]))
        source = {"schema_version":1,"authoring":GENERATOR,"case_id":spec.case_id,"mesh":mesh_records[spec.mesh_kind],
                  "albedo_recipe":{"kind":"piecewise_constant_uv_quadrants_and_four_stripes","version":1,
                      "intentional_asymmetry":variant=="intentional_asymmetry","reference_injection":reference_injection,
                      "target_injection":target_injection,"scalar_gain_applied_in_linear_rgb":spec.gain},
                  "camera_recipe":"elevation=0; right=(cos(az),sin(az),0), up=(0,0,1), backward=(sin(az),-cos(az),0); ray origin=right*(2u-1)*(abs(cos)+abs(sin))+up*(2v-1)+3*backward; direction=-backward",
                  "raster_recipe":"bottom-left endpoint samples u=x/(width-1),v=y/(height-1); no antialiasing; PNG rows top-left",
                  "authoring_tie_policy":"Stable smallest authored triangle index for image creation only. Coincident independent surfaces remain ambiguous truth, not disambiguated by this policy.",
                  "named_region":region,"truth_kind":"original_mathematical_authorship","human_reviewed":False}
        source_data = canonical_json(source)
        source_path = f"sources/{spec.case_id}.json"
        (destination/source_path).write_bytes(source_data)
        for variant_record in variants:
            for role, image_record in variant_record["views"].items():
                mode = "calibrated" if role=="target" and spec.photometry=="controlled-neutral-gain-srgb" else \
                       "lit" if role=="target" and spec.photometry=="uncontrolled-lit-srgb" else "albedo"
                image_record["appearance_settings"] = {
                    "color_space":"sRGB", "photometry":mode,
                    "linear_gain":spec.gain if mode=="calibrated" else 1.0,
                    "verified":True,
                    "evidence":{"artifact_id":"analytic-appearance-proof","sha256":sha256(source_data),
                                "media_type":"application/json","uri":"analytic-source.json"}}
        cases.append({"case_id":spec.case_id,"split":spec.split,"scope":spec.scope,"injection":spec.injection,
                      "source":{"path":source_path,"sha256":sha256(source_data)},"mesh":mesh_records[spec.mesh_kind],
                      "canonical":{"validated":True,"proof_kind":"exact_original_mathematical_authorship",
                                   "human_reviewed":False,"proof_sha256":sha256(source_data)},
                      "lineage_scenario":spec.lineage,"photometry":spec.photometry,"surface_region":region,
                      "semantic_service":{"kind":"mock-adapter-only" if spec.service!="not-configured" else "not-configured",
                                          "scenario":spec.service,"real_provider_calls":0,"semantic_quality_qualification":False},
                      "upstream":{"kind":"geometry_failure_contract_specimen","native_geometry_execution":False,
                                  "required_retained_code":"geometry.cross_view_conflict","required_retained_status":"fail"}
                                 if spec.injection=="upstream_geometry_fail" else None,
                      "expected":expected(spec),"variants":variants})
    panel_data = case_panel(panel)
    panel_path = "case-panel.png"
    (destination/panel_path).write_bytes(panel_data)
    authorities = {}
    for name in ("authoring.py","fixtures.py","preview.py"):
        authorities[name] = sha256((Path(__file__).parent/name).read_bytes().replace(b"\r\n",b"\n"))
    manifest = {"schema_version":SCHEMA_VERSION,"corpus_version":CORPUS_VERSION,"generator":GENERATOR,
        "generator_source_sha256_lf_normalized":authorities,
        "license":"GPL-3.0-or-later; original mathematical regression data under the existing repository license",
        "provenance":{"external_assets":[],"human_reviewed":False,"ai_generated":False,"provider_calls":0,"paid_cost":0,
                      "renderer":"Independent brute-force ray/triangle fixture authoring; no diagnostic BVH/UV/visibility implementation used"},
        "partition_policy":"Case parameters, epistemic labels and expectations frozen before diagnostic evaluation; no fitting to heldout results. Later reruns are exposed-holdout regression evidence.",
        "execution_plan":{"raster_resolutions":RASTERS,"orders":["canonical","reverse","rotate"],
                          "service_mock_cases":"Adapter qualification only, never real semantic-analyzer fidelity", "default_max_seconds_per_analysis":15},
        "scope":{"qualified_by_this_data":"Only stated analytic surface colour/pattern consistency and explicit abstentions",
                 "semantic_identity_general":"unknown; no human-approved generated pairs or real semantic analyzer qualification",
                 "hidden_surfaces_topology":"unknown","D5_D8":"unknown","initial_D7_and_issue_84":"open"},
        "review_panel":{"path":panel_path,"sha256":sha256(panel_data),"human_reviewed":False,"used_as_diagnostic_input":False},
        "cases":cases}
    (destination/"manifest.json").write_bytes(canonical_json(manifest))
    return manifest
