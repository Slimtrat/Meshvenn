"""Gate all authored Motion clips on independently fitted unrigged GLBs."""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT.parent))

import bpy
from scripts.glb_v2_motion_metrics import FIXTURES, compare_motion, check_motion, compare_pelvis_height, check_pelvis_height
from scripts.glb_v2_motion_support import prepare_target, observe_target, observe_export
from scripts.glb_v2_contact_metrics import (
    compare_contacts, check_contact_budgets, compare_contact_roundtrip, check_contact_roundtrip,
    contact_acceptance, CONTACT_BAND, MAX_VERTICAL_SPEED, MIN_WINDOW_SECONDS,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset",choices=tuple(FIXTURES),default="rigged_figure")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fps",type=int,choices=(24,60),default=60)
    parser.add_argument("--diagnostic-only",action="store_true")
    parser.add_argument("--preserve-pelvis-height",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    if args.fps != 60 and not args.diagnostic_only:
        parser.error("Contact regression gates require 60 Hz; use --diagnostic-only for 24 Hz")
    contact_budgets = contact_acceptance(args.asset,preserve_pelvis_height=args.preserve_pelvis_height)
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = args.fps
    filename,profile,expected_count,static = FIXTURES[args.asset]
    path = ROOT/"example"/"v2"/"assets"/filename
    context,pipeline,rig,reference,height,detected,neutral = prepare_target(path,output,observe_contacts=True)
    if detected != profile or len(reference["clips"]) != expected_count:
        raise AssertionError("Pinned Motion fixture lost its expected profile or clips")
    context.metadata["motion_source_path"] = str(path)
    context.metadata["motion_preserve_pelvis_height"] = args.preserve_pelvis_height
    module = importlib.import_module(f"{ROOT.name}.implementations.canonical_motion")
    result = module.CanonicalMotionRetargetImplementation().execute(context)
    if not result.success:
        raise AssertionError(result.message)
    motion = result.payload
    context.set_output(pipeline.PipelineStage.MOTION,motion)
    candidate = observe_target(rig,motion,reference,height)
    report = {"schema_version":2, "asset":args.asset, "profile":profile, "fps":args.fps,
              "preserve_pelvis_height":args.preserve_pelvis_height,
              "scope":"world-rest bone rotation deltas, in-place root and optional pelvis height; not anatomy or object motion",
              "input":{"sha256":neutral.sha256, "skin_count":neutral.skin_count,
                       "source_rig_available_to_fitter":False},
              "acceptance":{"integer_rotation_degrees":.05, "interframe_rotation_degrees":3,
                            "in_place_root_translation_in_heights":1e-5,
                            "integer_pelvis_height_error_in_heights":1e-5,
                            "interframe_pelvis_height_error_in_heights":.003,
                            "export_pelvis_height_fidelity_in_heights":1e-4,
                            "dense_sole_roundtrip_error_in_heights":1e-4},
              "reference":reference, "candidate":candidate,
              "retarget":compare_motion(reference,candidate,static_clips=static),
              "contact_scope":"fixed source-labelled sole patches; inferred near-ground intervals, not authored contacts or physics",
              "contact_policy":{"source_foot_descendant_weight":.7,"rest_sole_band_in_heights":.02,
                                "ground_band_in_heights":CONTACT_BAND,"max_vertical_speed_in_heights_per_second":MAX_VERTICAL_SPEED,
                                "min_window_seconds":MIN_WINDOW_SECONDS,"regression_budgets":contact_budgets},
              "pelvis_height":compare_pelvis_height(reference,candidate,preserved=args.preserve_pelvis_height),
              "contacts":compare_contacts(reference["contacts"],candidate["contacts"])}
    report_path = output/"report.json"
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if not args.diagnostic_only:
        check_motion(reference,candidate,static_clips=static)
        check_pelvis_height(reference,candidate,preserved=args.preserve_pelvis_height)
        if contact_budgets:
            report["contacts"] = check_contact_budgets(reference["contacts"],candidate["contacts"],contact_budgets)
    context.metadata.update(export_output_path=str(output/"canonical_motion.glb"),
                            export_overwrite_existing=True,export_validate_roundtrip=True)
    exporter = importlib.import_module(f"{ROOT.name}.implementations.glb_export")
    exported = exporter.GLBExportImplementation().execute(context)
    if not exported.success:
        raise AssertionError(exported.message)
    fidelity = exported.payload.metadata.get("roundtrip")
    if not fidelity or fidelity.get("passed") is not True or fidelity.get("sha256") != exported.payload.sha256:
        raise AssertionError("Published Motion GLB has no matching export-fidelity evidence")
    after = observe_export(exported.payload.path,rig,motion,reference,height)
    report.update(export={**exported.payload.metrics,"sha256":exported.payload.sha256,"roundtrip":fidelity},
                  imported=after,roundtrip=compare_motion(reference,after,static_clips=static),
                  export_rotation_fidelity=compare_motion(candidate,after,static_clips=static),
                  imported_contacts=compare_contacts(reference["contacts"],after["contacts"]))
    report["imported_pelvis_height"] = compare_pelvis_height(reference,after,preserved=args.preserve_pelvis_height)
    report["export_pelvis_height_fidelity"] = compare_pelvis_height(candidate,after,preserved=True)
    # Fidelity is enforced even in diagnostic mode; diagnostic-only relaxes
    # quality budgets, never whether the published GLB reproduces the target.
    report["export_sole_fidelity"] = compare_contact_roundtrip(candidate["contacts"],after["contacts"])
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    check_contact_roundtrip(candidate["contacts"],after["contacts"])
    if not args.diagnostic_only:
        check_motion(reference,after,static_clips=static)
        # Export must preserve the baked target, not merely fit a looser source budget.
        check_motion(candidate,after,static_clips=static,interframe_limit=.05)
        check_pelvis_height(reference,after,preserved=args.preserve_pelvis_height,integer_limit=1e-4,interframe_limit=.0031)
        check_pelvis_height(candidate,after,preserved=True,integer_limit=1e-4,interframe_limit=1e-4)
        if contact_budgets:
            report["imported_contacts"] = check_contact_budgets(reference["contacts"],after["contacts"],contact_budgets)
        report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"Motion V2 {args.asset}: {expected_count} clips, "
          f"integer={report['roundtrip']['max_integer_rotation_error_degrees']:.5f}deg, "
          f"interframe={report['roundtrip']['max_interframe_rotation_error_degrees']:.4f}deg")


if __name__ == "__main__":
    main()
