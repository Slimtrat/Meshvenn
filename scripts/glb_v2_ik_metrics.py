"""Independent IK scope and sole trajectory checks; baseline gates stay strict."""
from __future__ import annotations

import math

from core.motion_contacts import SIDES, contact_windows, contact_envelope
from scripts.glb_v2_motion_metrics import ROLES, _clips, angular_error
from scripts.glb_v2_contact_metrics import _matching, compare_contacts, validate_observations


def integer_surfaces(report):
    validate_observations(report)
    return {"probes":report["probes"],"sample_step":1,
            "clips":[{**clip,"samples":[sample for sample in clip["samples"] if float(sample["frame"]).is_integer()]}
                     for clip in report["clips"]]}


def check_ik_contact_quality(reference, baseline, candidate, *, budgets):
    report = compare_ik_contacts(reference,baseline,candidate)
    clips = {clip["name"]:clip for clip in report["clips"]}
    measured = []
    for name,budget in budgets.items():
        if name not in clips:
            raise AssertionError(f"Missing IK contact clip: {name}")
        counts = budget["source_windows"]
        if set(counts) != set(SIDES) or any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError("IK source window counts must be bilateral nonnegative integers")
        clip = clips[name]
        for side in SIDES:
            if sum(window["side"] == side for window in clip["windows"]) != budget["source_windows"][side]:
                raise AssertionError("IK contact coverage changed")
        if not clip["windows"]: continue
        if clip["target"]["penetration"] > 2e-5 or clip["target"]["hover"] > .012:
            raise AssertionError(f"IK contact floor quality failed: {name}/{clip['target']}")
        if clip["relative_path_errors_in_heights"]["target"] > .005:
            raise AssertionError(f"IK source-relative path changed: {name}")
        measured.append(name)
    report["gated_clip_names"] = measured
    report["unmeasured_clip_names"] = [name for name in budgets if name not in measured]
    return report


def check_ik_interframes(reference, candidate, *, budgets):
    source, target = validate_observations(reference), validate_observations(candidate)
    if (source.keys() != target.keys() or reference["probes"] != candidate["probes"]
            or reference.get("sample_step",1) != 1 or candidate.get("sample_step") != .5):
        raise AssertionError("IK interframes need matching clips and half-frame coverage")
    samples, penetration, hover, worst = 0, 0., 0., None
    for name in budgets:
        before,after = source[name],target[name]
        if any(before[k] != after[k] for k in ("frame_start","frame_end","fps")):
            raise AssertionError("IK interframe timing changed")
        for side in SIDES:
            for run in contact_windows(before,side):
                start,end = before["samples"][run[0]]["frame"],before["samples"][run[-1]]["frame"]
                for sample in after["samples"]:
                    if start <= sample["frame"] <= end and not float(sample["frame"]).is_integer():
                        low = sample["feet"][side]["min_z"]
                        samples += 1
                        if -low > penetration:
                            penetration, worst = -low, {"clip":name,"side":side,"frame":sample["frame"]}
                        hover = max(hover,low)
    if penetration > .001 or hover > .012:
        raise AssertionError(f"IK between-frame floor quality failed: {worst}, penetration={penetration}, hover={hover}")
    return {"contact_sole_sample_count":samples,"max_penetration_in_heights":penetration if samples else None,
            "max_hover_in_heights":hover if samples else None,"worst_penetration_sample":worst}


def check_ik_motion(baseline, candidate, contact_reference):
    originals, targets = _clips(baseline), _clips(candidate)
    source = validate_observations(contact_reference)
    if contact_reference.get("sample_step",1) != 1:
        raise AssertionError("Contact IK scope needs integer-frame source windows")
    if originals.keys() != targets.keys() or originals.keys() != source.keys():
        raise AssertionError("Contact IK lost clips")
    protected = {"integer": 0., "interframe": 0.}
    untouched, changed = 0., 0.
    for name, original in originals.items():
        target = targets[name]
        if any(original[k] != target[k] or original[k] != source[name][k] for k in ("frame_start", "frame_end", "fps")):
            raise AssertionError("Contact IK changed timing")
        windows = {side: contact_windows(source[name], side) for side in SIDES}
        for before, after in zip(original["samples"], target["samples"]):
            kind = "integer" if float(before["frame"]).is_integer() else "interframe"
            index = before["frame"] - original["frame_start"]
            for role in ROLES:
                error = angular_error(before["rotations"][role], after["rotations"][role])
                if not role.startswith(("thigh.", "shin.")):
                    protected[kind] = max(protected[kind], error)
                else:
                    active = any(contact_envelope(i,windows[role[-1]],original["fps"])[1] > 0
                                 for i in (math.floor(index), math.ceil(index)))
                    if active: changed = max(changed,error)
                    else: untouched = max(untouched,error)
            if math.hypot(*after["root_offset_in_heights"]) > 1e-5:
                raise AssertionError("Contact IK moved the root")
    if protected["integer"] > .05 or protected["interframe"] > 3 or untouched > .05:
        raise AssertionError(f"Contact IK changed a protected role or inactive leg: {protected}/{untouched}")
    return {"protected_rotation_errors_degrees":protected,
            "max_inactive_leg_error_degrees":untouched,"max_active_leg_change_degrees":changed}


def compare_ik_contacts(reference, baseline, candidate):
    sources, before = _matching(reference, baseline)
    _, after = _matching(reference, candidate)
    report = compare_contacts(reference, candidate)
    for clip in report["clips"]:
        name = clip["name"]
        path_errors = {"baseline":[],"target":[]}
        for side in SIDES:
            for run in contact_windows(sources[name],side):
                origin = sources[name]["samples"][run[0]]["feet"][side]["centroid"]
                anchor = before[name]["samples"][run[0]]["feet"][side]["centroid"]
                for index in run:
                    source = sources[name]["samples"][index]["feet"][side]["centroid"]
                    for label,data in (("baseline",before),("target",after)):
                        point = data[name]["samples"][index]["feet"][side]["centroid"]
                        path_errors[label].append(math.hypot(*(point[i]-anchor[i]-(source[i]-origin[i]) for i in (0,1))))
        clip["relative_path_errors_in_heights"] = {label:max(values) if values else None for label,values in path_errors.items()}
    return report
