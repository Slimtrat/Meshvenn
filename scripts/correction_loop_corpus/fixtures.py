"""Original assets and independent D6 expectations; imports no loop machine."""
from __future__ import annotations

from pathlib import Path
import struct

from scripts.appearance_diagnostic_corpus.authoring import canonical_json, png_rgba, sha256
from . import CORPUS_VERSION, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
PARENTS = {
    "appearance": {"path":"tests/fixtures/diagnostics/appearance-v1/manifest.json",
                   "sha256":"5fc81e9563bd6ee03ebc5b6f8b2f2eb003b8283aaa04a1f481788f6b4533d5e3"},
    "plans": {"path":"tests/fixtures/diagnostics/correction-plan-v1/manifest.json",
              "sha256":"c6e20ec65dcfcd00471edc4483db54ce8fcb42e6adce9fe7159baf18658b4567"},
}
COMMON = ("original_photo_and_source_bytes_unchanged", "original_GLB_artifact_bytes_unchanged",
          "canonical_reference_unchanged", "attempts_and_receipts_journalled",
          "no_real_provider_or_model_quality_qualification", "never_promote_before_global_evaluation")


def scenario(identifier, split, *, controls, outcomes=(), provider="normal", budget=None, **options):
    return {"case_id":identifier,"split":split,"scope":"orchestration-only",
            "provider_behavior":provider,"evaluation_outcomes":list(outcomes),
            "budgets":{"max_attempts":3,"max_seconds":10.,"max_cost":1.,"stagnation_limit":2,**(budget or {})},
            "options":options,"expected":{"controls":list(COMMON+tuple(controls))}}


def definitions():
    cases = [
        scenario("globally_improved_promoted","calibration",outcomes=("all_required_pass",),
            controls=("provider_called","global_evaluation_ran","promoted_after_full_reevaluation","accepted_candidate_is_measured_candidate")),
        scenario("higher_mean_erased_part_rejected","heldout",outcomes=("higher_mean_part_failure",),budget={"max_attempts":1},
            controls=("higher_mean_retained","named_part_failure_retained","not_promoted","rollback_restores_initial_asset")),
        scenario("identity_failure_rejected","calibration",outcomes=("identity_failure",),budget={"max_attempts":1},
            controls=("required_identity_failure_retained","not_promoted","rollback_restores_initial_asset")),
        scenario("required_unknown_never_passes","heldout",outcomes=("required_unknown",),budget={"max_attempts":1},
            controls=("required_unknown_retained","no_unknown_to_pass_coercion","not_promoted")),
        scenario("rollback_all_original_bytes","heldout",outcomes=("identity_failure",),budget={"max_attempts":1},
            controls=("candidate_materialized_separately","not_promoted","rollback_restores_initial_asset","photo_source_GLB_hashes_exact")),
        scenario("attempt_budget","calibration",outcomes=("no_progress","no_progress","all_required_pass"),
            budget={"max_attempts":2,"stagnation_limit":3},
            controls=("attempt_limit_respected","exactly_two_provider_calls","not_promoted","budget_stop_explicit")),
        scenario("time_budget","heldout",outcomes=("no_progress",),budget={"max_seconds":1.},evaluation_clock_advance=2.,
            controls=("time_limit_respected","no_new_call_after_deadline","not_promoted","budget_stop_explicit")),
        scenario("cost_budget","calibration",outcomes=("no_progress","all_required_pass"),
            budget={"max_cost":.25},quote_cost=.2,receipt_cost=.2,
            controls=("cost_limit_respected","exactly_one_provider_call","cost_reservation_precedes_dispatch","not_promoted")),
        scenario("stagnation_budget","heldout",outcomes=("no_progress","no_progress","all_required_pass"),
            budget={"max_attempts":5,"stagnation_limit":2},
            controls=("stagnation_stop_explicit","bounded_calls","not_promoted")),
        scenario("service_failure","calibration",provider="service_error",budget={"max_attempts":1},
            controls=("failure_journalled","bounded_calls","not_promoted","rollback_restores_initial_asset")),
        scenario("late_response","heldout",provider="late_response",outcomes=("all_required_pass",),
            budget={"max_seconds":1.},provider_clock_advance=2.,
            controls=("late_receipt_retained","late_candidate_not_promoted","cost_not_erased","not_promoted")),
        scenario("cancellation","calibration",provider="cancel_during_call",outcomes=("all_required_pass",),
            controls=("cancelled_state_retained","no_new_call_after_cancel","not_promoted","rollback_restores_initial_asset")),
        scenario("crash_pending_resume_uncertain","heldout",provider="crash_after_dispatch",budget={"max_attempts":2},
            controls=("durable_pending_before_dispatch","restart_reads_actual_journal","uncertain_attempt_not_redispatched",
                      "explicit_uncertainty_retained","not_promoted")),
        scenario("provider_unavailable_keeps_local_plans","calibration",provider="unavailable",
            controls=("no_provider_dispatch","local_plans_preserved","provider_unavailable_explicit","not_promoted")),
        scenario("canonical_never_provisional_mesh","heldout",outcomes=("no_progress","all_required_pass"),
            controls=("canonical_hash_identical_for_every_call","provisional_mesh_never_reference","global_evaluation_ran")),
        scenario("receipt_audit","calibration",outcomes=("all_required_pass",),quote_cost=.2,receipt_cost=.2,
            controls=("provider_model_params_usage_preserved","receipt_request_binding_exact","all_dispatches_auditable")),
        scenario("real_D2_D4_improvement_identity_unknown","heldout",outcomes=("real_D2_D4",),budget={"max_attempts":1},
            controls=("real_preflight_and_appearance_ran","numeric_region_improves_fail_to_pass","real_identity_stays_unknown",
                      "required_unknown_retained","not_promoted")),
        scenario("evaluation_failure_after_receipt","calibration",outcomes=("evaluation_error",),budget={"max_attempts":1},
            controls=("receipt_survives_evaluation_failure","failure_journalled","not_promoted","rollback_restores_initial_asset")),
    ]
    for case in cases:
        if case["case_id"]=="real_D2_D4_improvement_identity_unknown":
            case["scope"]="real-diagnostics-plus-simulated-provider"
            case["real_source"]={"parent":"appearance","case_id":"local_colour_change","raster_resolution":32,
                                 "candidate_recipe":"original accepted source rendered without the authored local colour defect"}
    return cases


def triangle_glb(scale=1.):
    """An original single triangle, not a certified exported production asset."""
    points = ((-.5*scale,0.,-.5*scale),(.5*scale,0.,-.5*scale),(0.,0.,.5*scale))
    binary = b"".join(struct.pack("<3f",*point) for point in points)+struct.pack("<3H",0,1,2)
    document = {"asset":{"version":"2.0","generator":"Original D6 corpus mathematical triangle"},
        "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
        "meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1}]}],
        "buffers":[{"byteLength":len(binary)}],
        "bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":36,"target":34962},
                       {"buffer":0,"byteOffset":36,"byteLength":6,"target":34963}],
        "accessors":[{"bufferView":0,"componentType":5126,"count":3,"type":"VEC3",
                      "min":[-.5*scale,0.,-.5*scale],"max":[.5*scale,0.,.5*scale]},
                     {"bufferView":1,"componentType":5123,"count":3,"type":"SCALAR","min":[0],"max":[2]}]}
    data = canonical_json(document).rstrip(b"\n")
    data += b" "*((-len(data))%4)
    binary += b"\0"*((-len(binary))%4)
    return struct.pack("<4sII",b"glTF",2,12+8+len(data)+8+len(binary))+struct.pack("<I4s",len(data),b"JSON")+data+struct.pack("<I4s",len(binary),b"BIN\0")+binary


def authored_image(*, defective=False, erased_part=False):
    data = bytearray()
    for y in range(32):
        for x in range(32):
            body = 9<=x<23 and 5<=y<27
            part = 23<=x<27 and 16<=y<20 and not erased_part
            rgb = (150,50,170) if defective and 11<=x<16 and 9<=y<14 else (55,115,185)
            data.extend((*rgb,255) if body or part else (0,0,0,0))
    return bytes(data)


def build_corpus(destination):
    destination.mkdir(parents=True,exist_ok=True)
    assets = []
    def save(name,data):
        path = destination/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
        assets.append({"path":name,"sha256":sha256(data),"bytes":len(data)})
    for name,rgba in (("original-photo",authored_image(defective=True)),
                      ("accepted-reference",authored_image()),("candidate-improved",authored_image()),
                      ("candidate-erased-part",authored_image(erased_part=True))):
        save("assets/"+name+".png",png_rgba(32,32,rgba,author_tag="original-d6-"+name))
    save("assets/original.glb",triangle_glb())
    save("assets/candidate.glb",triangle_glb(.98))
    proof={"schema_version":1,"author":"Original mathematical fixture, no real photograph or outside asset.",
           "original_photo":"Analytic user-origin stand-in; source bytes are immutable.",
           "shape":"body x[9,23),y[5,27), appendage x[23,27),y[16,20), raster32 bottom-left",
           "intentional_asymmetry":True,"GLB":"Original one-triangle glTF binary, byte-preservation contract only.",
           "canonical":"Original accepted analytic reference; never a reconstructed or provider candidate.",
           "human_reviewed":False,"provider_fidelity_qualified":False,"semantic_model_qualified":False}
    save("original-source.json",canonical_json(proof))
    generator=[{"path":name,"sha256_lf":sha256((ROOT/name).read_bytes().replace(b"\r\n",b"\n"))}
               for name in ("scripts/correction_loop_corpus/fixtures.py","scripts/appearance_diagnostic_corpus/authoring.py")]
    manifest={"schema_version":SCHEMA_VERSION,"corpus_version":CORPUS_VERSION,
        "expectations_frozen_before_loop_evaluation":True,"parents":PARENTS,"assets":assets,
        "provenance":{"kind":"original_analytic_contract_corpus","human_reviewed":False,
                      "real_provider_calls":0,"provider_fidelity_qualified":False,"generator_sources":generator},
        "port_metadata":{"provider_id":"corpus.provider_simulator","provider_version":"1",
                         "model_id":"corpus.fixed_model","model_version":"1",
                         "parameters":{"seed":17,"strength":.3},
                         "usage":{"input_units":12,"output_units":8,"images":1},"default_quote_cost":.2},
        "simulated_evaluation":{"baseline_mean_iou":.8,"improved_mean_iou":.95,"part_erased_mean_iou":.98,
            "meaning":"Contract data reported by local fake ports, not measured NativeCore fidelity or model judgment quality."},
        "clock":{"kind":"deterministic_host_test_clock","initial_seconds":0.,
                 "meaning":"Only orchestration deadline controls; no wall-clock performance claim is inferred from logical time."},
        "cases":definitions(),
        "limits":{"provider_fidelity":"unqualified","semantic_identity":"unqualified",
                  "physical_geometry_and_export_quality":"unqualified","real_D2_D4_identity":"unknown",
                  "initial_D7_and_issue_84":"open"}}
    data=canonical_json(manifest)
    (destination/"manifest.json").write_bytes(data)
    return manifest,sha256(data)
