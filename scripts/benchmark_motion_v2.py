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
from scripts.glb_v2_motion_metrics import FIXTURES, compare_motion, check_motion
from scripts.glb_v2_motion_support import prepare_target, observe_target, observe_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset",choices=tuple(FIXTURES),default="rigged_figure")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--fps",type=int,choices=(24,60),default=60)
    parser.add_argument("--diagnostic-only",action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = args.fps
    filename,profile,expected_count,static = FIXTURES[args.asset]
    path = ROOT/"example"/"v2"/"assets"/filename
    context,pipeline,rig,reference,height,detected,neutral = prepare_target(path,output)
    if detected != profile or len(reference["clips"]) != expected_count:
        raise AssertionError("Pinned Motion fixture lost its expected profile or clips")
    context.metadata["motion_source_path"] = str(path)
    module = importlib.import_module(f"{ROOT.name}.implementations.canonical_motion")
    result = module.CanonicalMotionRetargetImplementation().execute(context)
    if not result.success:
        raise AssertionError(result.message)
    motion = result.payload
    context.set_output(pipeline.PipelineStage.MOTION,motion)
    candidate = observe_target(rig,motion,reference,height)
    report = {"schema_version":1, "asset":args.asset, "profile":profile, "fps":args.fps,
              "scope":"world-rest bone rotation deltas and in-place root; not anatomy, contact, object motion, translation or skin quality",
              "input":{"sha256":neutral.sha256, "skin_count":neutral.skin_count,
                       "source_rig_available_to_fitter":False},
              "acceptance":{"integer_rotation_degrees":.05, "interframe_rotation_degrees":3,
                            "in_place_root_translation_in_heights":1e-5},
              "reference":reference, "candidate":candidate,
              "retarget":compare_motion(reference,candidate,static_clips=static)}
    report_path = output/"report.json"
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if not args.diagnostic_only:
        check_motion(reference,candidate,static_clips=static)
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
                  export_rotation_fidelity=compare_motion(candidate,after,static_clips=static))
    report_path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    if not args.diagnostic_only:
        check_motion(reference,after,static_clips=static)
        # Export must preserve the baked target, not merely fit a looser source budget.
        check_motion(candidate,after,static_clips=static,interframe_limit=.05)
    print(f"Motion V2 {args.asset}: {expected_count} clips, "
          f"integer={report['roundtrip']['max_integer_rotation_error_degrees']:.5f}deg, "
          f"interframe={report['roundtrip']['max_interframe_rotation_error_degrees']:.4f}deg")


if __name__ == "__main__":
    main()
