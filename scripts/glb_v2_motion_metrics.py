"""Independent world-rest rotation fidelity, not anatomical motion quality."""
from __future__ import annotations

import math

ROLES = ("pelvis", "spine", "chest", "neck", "head",
         *(f"{part}.{side}" for side in ("L", "R") for part in ("upper_arm", "forearm", "hand")),
         *(f"{part}.{side}" for side in ("L", "R") for part in ("thigh", "shin", "foot")))
FIXTURES = {
    "rigged_figure": ("RiggedFigure.glb", "rigged-figure-v1", 1, ()),
    "quaternius_human": ("QuaterniusHuman.glb", "mixamo-humanoid-v1", 7, ()),
    "quaternius_ual1": ("UAL1_Standard.glb", "unreal-mannequin-v1", 43,
                       ("A_TPose", "Pistol_Aim_Down", "Pistol_Aim_Neutral", "Pistol_Aim_Up")),
}


def compare_pelvis_height(reference, candidate, *, preserved):
    if type(preserved) is not bool:
        raise ValueError("Pelvis height preservation must be boolean")
    originals, targets = _clips(reference), _clips(candidate)
    if originals.keys() != targets.keys():
        raise AssertionError("Pelvis height lost a clip")
    worst = {"integer": (0., None), "interframe": (0., None)}
    for name, clip in originals.items():
        target = targets[name]
        if any(clip[k] != target[k] for k in ("frame_start", "frame_end", "fps")):
            raise AssertionError("Pelvis height timing changed")
        for before, after in zip(clip["samples"], target["samples"]):
            source_height, height = before["pelvis_height_offset_in_heights"], after["pelvis_height_offset_in_heights"]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (source_height, height)):
                raise ValueError("Pelvis height observations must be finite")
            error = abs(height - (source_height if preserved else 0.))
            kind = "integer" if float(before["frame"]).is_integer() else "interframe"
            if error >= worst[kind][0]: worst[kind] = (error, {"clip": name, "frame": before["frame"]})
    return {kind: {"max_error_in_heights": value, "worst_sample": sample} for kind, (value, sample) in worst.items()}


def check_pelvis_height(reference, candidate, *, preserved, integer_limit=1e-5, interframe_limit=.003):
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (integer_limit, interframe_limit)):
        raise ValueError("Pelvis height limits must be finite and nonnegative")
    report = compare_pelvis_height(reference, candidate, preserved=preserved)
    for kind, limit in (("integer", integer_limit), ("interframe", interframe_limit)):
        if report[kind]["max_error_in_heights"] > limit:
            raise AssertionError(f"Pelvis height {kind} transfer changed: {report[kind]}")
    return report


def sample_frames(start, end):
    if any(type(v) not in (int,float) or not math.isfinite(v) or not float(v).is_integer()
           for v in (start,end)) or end <= start:
        raise ValueError("Motion needs an increasing integer frame range")
    start,end = int(start),int(end)
    knots = sorted({round(start+(end-start)*i/8) for i in range(9)})
    return tuple(sorted({*knots, *(frame+.5 for frame in knots if frame < end)}))


def _quaternion(values):
    if len(values) != 4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise ValueError("Expected a finite quaternion")
    norm = math.hypot(*values)
    if norm < 1e-12:
        raise ValueError("Zero quaternion is not an orientation")
    return tuple(v/norm for v in values)


def angular_error(a, b):
    a,b = _quaternion(a),_quaternion(b)
    dot = min(1.0, abs(sum(x*y for x,y in zip(a,b))))
    return math.degrees(2*math.acos(dot))


def _clips(report):
    clips = report["clips"]
    if not clips or len({c["name"] for c in clips}) != len(clips):
        raise ValueError("Missing or duplicated Motion clips")
    for clip in clips:
        fps = clip["fps"]
        if type(fps) not in (int,float) or not math.isfinite(fps) or fps <= 0:
            raise ValueError("Invalid Motion FPS")
        frames = sample_frames(clip["frame_start"],clip["frame_end"])
        if tuple(s["frame"] for s in clip["samples"]) != frames:
            raise ValueError("Missing or changed Motion sample instants")
        for sample in clip["samples"]:
            if set(sample["rotations"]) != set(ROLES):
                raise ValueError("Missing canonical Motion role")
            for value in sample["rotations"].values():
                _quaternion(value)
            point = sample["root_offset_in_heights"]
            if len(point) != 3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):
                raise ValueError("Invalid Motion root position")
    return {clip["name"]:clip for clip in clips}


def compare_motion(reference, candidate, *, static_clips=()):
    """Inspect every role/sample; preserve worst cases rather than averages."""
    originals,targets = _clips(reference),_clips(candidate)
    if originals.keys() != targets.keys() or not set(static_clips).issubset(originals):
        raise AssertionError("Motion changed or lost source clips")
    cases = []
    for name,source in originals.items():
        target = targets[name]
        if any(source[field] != target[field] for field in ("frame_start","frame_end","fps")):
            raise AssertionError(f"Motion changed source timing: {name}")
        integer_errors,between_errors,source_motion,target_motion,root_motion = [],[],[],[],[]
        for before,after in zip(source["samples"],target["samples"]):
            bucket = integer_errors if float(before["frame"]).is_integer() else between_errors
            for role in ROLES:
                bucket.append((angular_error(before["rotations"][role],after["rotations"][role]),before["frame"],role))
                source_motion.append(angular_error(source["samples"][0]["rotations"][role],before["rotations"][role]))
                target_motion.append(angular_error(target["samples"][0]["rotations"][role],after["rotations"][role]))
            root_motion.append(math.hypot(*after["root_offset_in_heights"]))
        worst_integer,worst_between = max(integer_errors),max(between_errors)
        cases.append({"name":name, "sample_count":len(source["samples"]),
                      "role_sample_count":len(source["samples"])*len(ROLES),
                      "static":name in static_clips,
                      "max_integer_rotation_error_degrees":worst_integer[0],
                      "max_interframe_rotation_error_degrees":worst_between[0],
                      "worst_integer_sample":{"frame":worst_integer[1],"role":worst_integer[2]},
                      "worst_interframe_sample":{"frame":worst_between[1],"role":worst_between[2]},
                      "source_rotation_change_degrees":max(source_motion),
                      "target_rotation_change_degrees":max(target_motion),
                      "max_root_translation_in_heights":max(root_motion)})
    return {"clip_count":len(cases), "role_sample_count":sum(c["role_sample_count"] for c in cases),
            "max_integer_rotation_error_degrees":max(c["max_integer_rotation_error_degrees"] for c in cases),
            "max_interframe_rotation_error_degrees":max(c["max_interframe_rotation_error_degrees"] for c in cases),
            "max_root_translation_in_heights":max(c["max_root_translation_in_heights"] for c in cases),
            "clips":cases}


def check_motion(reference, candidate, *, static_clips=(), interframe_limit=3.0):
    if not math.isfinite(interframe_limit) or interframe_limit < 0:
        raise ValueError("Invalid interframe rotation budget")
    report = compare_motion(reference,candidate,static_clips=static_clips)
    for clip in report["clips"]:
        if clip["max_integer_rotation_error_degrees"] > .05 or clip["max_interframe_rotation_error_degrees"] > interframe_limit:
            raise AssertionError(f"Motion rotation fidelity failed: {clip}")
        if clip["max_root_translation_in_heights"] > 1e-5:
            raise AssertionError(f"Motion root did not remain in place: {clip['name']}")
        variations = (clip["source_rotation_change_degrees"],clip["target_rotation_change_degrees"])
        if (max(variations) > .05 if clip["static"] else min(variations) < .1):
            raise AssertionError(f"Motion static/moving classification failed: {clip['name']}")
    return report
