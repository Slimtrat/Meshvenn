"""Gate opt-in contact IK separately from the unchanged rotation-only bake."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent))

import bpy
from scripts.glb_v2_motion_metrics import FIXTURES, check_motion, check_pelvis_height, compare_motion
from scripts.glb_v2_motion_support import prepare_target, observe_target, observe_export
from scripts.glb_v2_contact_metrics import compare_contacts, check_contact_roundtrip, contact_acceptance, check_contact_budgets
from scripts.glb_v2_ik_metrics import (
    check_ik_motion, compare_ik_contacts, integer_surfaces, check_ik_contact_quality, check_ik_interframes,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset",choices=tuple(FIXTURES),default="quaternius_human")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--diagnostic-only",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 60
    filename,profile,count,static = FIXTURES[args.asset]
    path = ROOT/"example/v2/assets"/filename
    context,pipeline,rig,reference,height,detected,neutral = prepare_target(path,output,observe_contacts=True)
    if detected != profile or len(reference["clips"]) != count:
        raise AssertionError("Pinned contact IK source changed")
    implementation = importlib.import_module(f"{ROOT.name}.implementations.canonical_motion").CanonicalMotionRetargetImplementation()
    context.metadata.update(motion_source_path=str(path),motion_preserve_pelvis_height=True)
    first = implementation.execute(context)
    if not first.success: raise AssertionError(first.message)
    baseline = observe_target(rig,first.payload,reference,height)
    check_motion(reference,baseline,static_clips=static)
    check_pelvis_height(reference,baseline,preserved=True)
    budgets = contact_acceptance(args.asset,preserve_pelvis_height=True)
    if budgets: check_contact_budgets(reference["contacts"],baseline["contacts"],budgets)
    context.metadata["motion_contact_ik"] = True
    corrected = implementation.execute(context)
    if not corrected.success: raise AssertionError(corrected.message)
    motion = corrected.payload
    context.set_output(pipeline.PipelineStage.MOTION,motion)
    candidate = observe_target(rig,motion,reference,height,surface_step=.5)
    candidate_half = candidate["contacts"]
    candidate["contacts"] = integer_surfaces(candidate_half)
    report = {"schema_version":1,"asset":args.asset,"profile":profile,"fps":60,
              "scope":"opt-in inferred flat-floor IK; source-relative sole path, not world locking or physics",
              "input_sha256":neutral.sha256,"source_rig_available_to_fitter":False,
              "acceptance":{"locomotion_source_windows":{name:budget["source_windows"] for name,budget in budgets.items()},
                            "integer_penetration_in_heights":2e-5,"half_frame_penetration_in_heights":.001,
                            "hover_in_heights":.012,"source_relative_xy_path_error_in_heights":.005,
                            "sole_export_fidelity_in_heights":1e-4,
                            "protected_rotations_degrees":{"integer":.05,"interframe":3},
                            "export_rotations_degrees":.05},
              "reference":reference,"baseline":baseline,"candidate":candidate,
              "half_frame_surfaces":candidate_half,
              "baseline_rotation_fidelity":compare_motion(reference,baseline,static_clips=static),
              "baseline_contacts":compare_contacts(reference["contacts"],baseline["contacts"]),
              "protected_motion":check_ik_motion(baseline,candidate,reference["contacts"]),
              "contacts":compare_ik_contacts(reference["contacts"],baseline["contacts"],candidate["contacts"]),
              "solver":motion.metrics["contact_ik"]}
    report_path = output/"report.json"
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    check_pelvis_height(reference,candidate,preserved=True)
    if not args.diagnostic_only:
        report["contacts"] = check_ik_contact_quality(reference["contacts"],baseline["contacts"],candidate["contacts"],budgets=budgets)
        report["interframe_contacts"] = check_ik_interframes(reference["contacts"],candidate_half,budgets=budgets)
    context.metadata.update(export_output_path=str(output/"contact_ik.glb"),export_overwrite_existing=True,
                            export_validate_roundtrip=True)
    exporter = importlib.import_module(f"{ROOT.name}.implementations.glb_export").GLBExportImplementation()
    result = exporter.execute(context)
    if not result.success: raise AssertionError(result.message)
    fidelity = result.payload.metadata.get("roundtrip")
    if not fidelity or fidelity.get("passed") is not True or fidelity.get("sha256") != result.payload.sha256:
        raise AssertionError("Contact IK GLB has no matching fidelity evidence")
    after = observe_export(result.payload.path,rig,motion,reference,height,surface_step=.5)
    after_half = after["contacts"]
    after["contacts"] = integer_surfaces(after_half)
    report.update(imported=after,export={"sha256":result.payload.sha256,"roundtrip":fidelity},
                  imported_contacts=compare_ik_contacts(reference["contacts"],baseline["contacts"],after["contacts"]),
                  export_sole_fidelity=check_contact_roundtrip(candidate["contacts"],after["contacts"]),
                  imported_half_frame_surfaces=after_half,
                  export_half_frame_sole_fidelity=check_contact_roundtrip(candidate_half,after_half),
                  export_rotation_fidelity=check_motion(candidate,after,static_clips=static,interframe_limit=.05))
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    check_ik_motion(baseline,after,reference["contacts"])
    check_pelvis_height(candidate,after,preserved=True,integer_limit=1e-4,interframe_limit=1e-4)
    if not args.diagnostic_only:
        report["imported_contacts"] = check_ik_contact_quality(reference["contacts"],baseline["contacts"],after["contacts"],budgets=budgets)
        report["imported_interframe_contacts"] = check_ik_interframes(reference["contacts"],after_half,budgets=budgets)
        report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    for clip in report["contacts"]["clips"]:
        if clip["name"] in budgets:
            print("IK",clip["name"],clip["coverage"],clip["target"],clip["relative_path_errors_in_heights"])
    print(f"Contact IK {args.asset}: {count} clips, sole fidelity {report['export_sole_fidelity']['max_error_in_heights']:.8f} heights")


if __name__ == "__main__": main()
