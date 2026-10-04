"""Source-defined sole-patch contact proxies; not authored contact or physics.

An in-place stance can travel at a nonzero treadmill velocity. Remove the
source window's fitted horizontal velocity from BOTH trajectories, never a
velocity fitted to the candidate (which could conceal added sliding).
"""
from __future__ import annotations

import math
from core.motion_contacts import SIDES, CONTACT_BAND, MAX_VERTICAL_SPEED, MIN_WINDOW_SECONDS, contact_windows

LOCOMOTION_CLIPS = {  # Explicit fixture labels, not a name-based classifier.
    "rigged_figure": (),
    "quaternius_human": ("Run", "Walk"),
    "quaternius_ual1": ("Crouch_Fwd_Loop", "Jog_Fwd_Loop", "Sprint_Loop",
                        "Walk_Formal_Loop", "Walk_Loop"),
}
# Measured regression ceilings, NOT acceptable contact/slide quality targets.
# (source L/R window counts, rotation-only limits, pelvis-height limits).
# Limits are (penetration, hover, source-velocity-detrended drift), in heights.
CONTACT_BASELINES = {
    "rigged_figure": {},
    "quaternius_human": {
        "Run": ((0, 0), None, None),
        "Walk": ((1, 3), (.013, .037, .047), (.034, .003, .047)),
    },
    "quaternius_ual1": {
        "Crouch_Fwd_Loop": ((1, 2), (.001, .24, .325), (.044, .003, .325)),
        "Jog_Fwd_Loop": ((1, 0), (.001, .105, .021), (.034, .002, .021)),
        "Sprint_Loop": ((0, 0), None, None),
        "Walk_Formal_Loop": ((1, 2), (.001, .020, .033), (.022, .004, .033)),
        "Walk_Loop": ((1, 2), (.005, .028, .033), (.022, .004, .033)),
    },
}


def contact_acceptance(asset, *, preserve_pelvis_height):
    if type(preserve_pelvis_height) is not bool:
        raise ValueError("Pelvis height option must be boolean")
    result = {}
    for name, (windows, rotation_only, pelvis_height) in CONTACT_BASELINES[asset].items():
        limits = pelvis_height if preserve_pelvis_height else rotation_only
        result[name] = {"source_windows": dict(zip(SIDES, windows)),
                        **dict(zip(("penetration", "hover", "drift"), limits or (None,) * 3))}
    return result


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def dense_frames(start, end, *, step=1):
    if any(not _finite(v) or not float(v).is_integer() for v in (start, end)) or end <= start:
        raise ValueError("Contact observations need an increasing integer frame range")
    if not _finite(step) or step not in (.5,1):
        raise ValueError("Contact sample step must be 0.5 or 1 frame")
    if step == .5: return tuple(int(start)+i/2 for i in range(2*(int(end)-int(start))+1))
    return tuple(range(int(start), int(end) + 1))


def validate_observations(report):
    probes = report["probes"]
    if set(probes) != set(SIDES):
        raise ValueError("Contact observations need both sole patches")
    for points in probes.values():
        if len(points) < 3 or len({tuple(p) for p in points}) != len(points):
            raise ValueError("Sole patches need three distinct rest positions")
        if any(len(p) != 3 or not all(_finite(v) for v in p) for p in points):
            raise ValueError("Sole rest positions must be finite 3D points")
    if {tuple(p) for p in probes["L"]} & {tuple(p) for p in probes["R"]}:
        raise ValueError("Bilateral sole patches cannot reuse a rest position")
    clips = report["clips"]
    if not clips or any(not isinstance(c["name"], str) or not c["name"] for c in clips):
        raise ValueError("Contact clips need names")
    if len({c["name"] for c in clips}) != len(clips):
        raise ValueError("Duplicated contact clips")
    for clip in clips:
        if not _finite(clip["fps"]) or clip["fps"] <= 0:
            raise ValueError("Contact FPS must be finite and positive")
        frames = dense_frames(clip["frame_start"], clip["frame_end"], step=report.get("sample_step",1))
        if any(not _finite(s["frame"]) for s in clip["samples"]) or tuple(s["frame"] for s in clip["samples"]) != frames:
            raise ValueError("Contact observations require every sample on the declared clock in order")
        for sample in clip["samples"]:
            if set(sample["feet"]) != set(SIDES):
                raise ValueError("Missing or extra sole patch")
            for foot in sample["feet"].values():
                point, low = foot["centroid"], foot["min_z"]
                if len(point) != 3 or not all(_finite(v) for v in (*point, low)):
                    raise ValueError("Sole observations must be finite")
                if low > point[2] + 1e-9:
                    raise ValueError("Sole minimum cannot exceed its centroid")
    return {clip["name"]: clip for clip in clips}


def _matching(reference, candidate):
    originals, targets = validate_observations(reference), validate_observations(candidate)
    if (reference["probes"] != candidate["probes"] or originals.keys() != targets.keys()
            or reference.get("sample_step",1) != candidate.get("sample_step",1)):
        raise AssertionError("Contact clips or frozen sole references changed")
    for name, original in originals.items():
        if any(original[k] != targets[name][k] for k in ("frame_start", "frame_end", "fps")):
            raise AssertionError(f"Contact timing changed: {name}")
    return originals, targets


def _velocity(points, fps, *, step=1):
    times = [i * step / fps for i in range(len(points))]
    center = sum(times) / len(times)
    denominator = sum((t - center) ** 2 for t in times)
    return tuple(sum((t - center) * p[axis] for t, p in zip(times, points)) / denominator
                 for axis in (0, 1))


def _window_score(samples, side, run, fps, velocity):
    feet = [samples[i]["feet"][side] for i in run]
    origin = feet[0]["centroid"]
    start = samples[run[0]]["frame"]
    drift = [math.hypot(*(foot["centroid"][axis] - origin[axis] - velocity[axis] * (samples[index]["frame"]-start) / fps
                          for axis in (0, 1))) for index, foot in zip(run,feet)]
    return {"penetration": max(0., -min(f["min_z"] for f in feet)),
            "hover": max(0., max(f["min_z"] for f in feet)),
            "drift": max(drift)}


def compare_contacts(reference, candidate):
    originals, targets = _matching(reference, candidate)
    clips = []
    for name, original in originals.items():
        windows = []
        for side in SIDES:
            for run in contact_windows(original, side):
                points = [original["samples"][i]["feet"][side]["centroid"] for i in run]
                velocity = _velocity(points, original["fps"], step=reference.get("sample_step",1))
                windows.append({"side": side,
                                "frame_start": original["samples"][run[0]]["frame"],
                                "frame_end": original["samples"][run[-1]]["frame"],
                                "source_velocity_in_heights_per_second": velocity,
                                "source": _window_score(original["samples"], side, run, original["fps"], velocity),
                                "target": _window_score(targets[name]["samples"], side, run, original["fps"], velocity)})
        summaries = {label: {metric: max(w[label][metric] for w in windows) if windows else None
                             for metric in ("penetration", "hover", "drift")}
                     for label in ("source", "target")}
        sides = {w["side"] for w in windows}
        coverage = "bilateral" if len(sides) == 2 else "single-foot" if sides else "unmeasured"
        clips.append({"name": name, "coverage": coverage, "window_count": len(windows), "windows": windows, **summaries})
    return {"clip_count": len(clips), "sole_sample_count": sum(len(c["samples"]) * 2 for c in originals.values()),
            "window_count": sum(c["window_count"] for c in clips), "clips": clips}


def check_contact_budgets(reference, candidate, budgets):
    report = compare_contacts(reference, candidate)
    clips = {c["name"]: c for c in report["clips"]}
    if not budgets:
        raise ValueError("Contact regression budgets cannot be empty")
    for name, budget in budgets.items():
        if name not in clips:
            raise AssertionError(f"Missing contact regression clip: {name}")
        clip = clips[name]
        for side in SIDES:
            expected = budget["source_windows"][side]
            if type(expected) is not int or expected < 0:
                raise ValueError("Source window counts must be nonnegative integers")
            if sum(w["side"] == side for w in clip["windows"]) != expected:
                raise AssertionError(f"Changed source contact coverage: {name}/{side}")
        if not clip["windows"]:
            if any(budget[metric] is not None for metric in ("penetration", "hover", "drift")):
                raise ValueError("Unmeasured clips cannot carry passing quality limits")
            continue
        for metric in ("penetration", "hover", "drift"):
            limit = budget[metric]
            if not _finite(limit) or limit < 0:
                raise ValueError("Contact regression limits must be finite and nonnegative")
            if clip["target"][metric] > limit:
                raise AssertionError(f"{name}: sole {metric} {clip['target'][metric]:.6f} > {limit:.6f} heights")
    report["gated_clip_names"] = [name for name in budgets if clips[name]["windows"]]
    report["unmeasured_clip_names"] = [name for name in budgets if not clips[name]["windows"]]
    return report


def compare_contact_roundtrip(reference, candidate, *, tolerance=1e-4):
    if not _finite(tolerance) or tolerance < 0:
        raise ValueError("Sole roundtrip tolerance must be finite and nonnegative")
    originals, targets = _matching(reference, candidate)
    errors = []
    for name, original in originals.items():
        for before, after in zip(original["samples"], targets[name]["samples"]):
            for side in SIDES:
                a, b = before["feet"][side], after["feet"][side]
                error = max(math.dist(a["centroid"], b["centroid"]), abs(a["min_z"] - b["min_z"]))
                errors.append((error, name, before["frame"], side))
    error, name, frame, side = max(errors)
    return {"sole_sample_count": len(errors), "max_error_in_heights": error,
            "worst_sample": {"clip": name, "frame": frame, "side": side}, "tolerance": tolerance}


def check_contact_roundtrip(reference, candidate, *, tolerance=1e-4):
    report = compare_contact_roundtrip(reference, candidate, tolerance=tolerance)
    if report["max_error_in_heights"] > tolerance:
        raise AssertionError(f"Sole roundtrip drift: {report['worst_sample']}: {report['max_error_in_heights']:.8f} heights")
    return report
