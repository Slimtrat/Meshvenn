"""Near-ground source windows; inferred proxies, never authored contacts."""
from __future__ import annotations

import math

SIDES = ("L", "R")
CONTACT_BAND = (-.015, .01)
MAX_VERTICAL_SPEED = .15
MIN_WINDOW_SECONDS = .08
BLEND_SECONDS = .08


def contact_windows(clip, side):
    fps, samples = clip["fps"], clip["samples"]
    if side not in SIDES or type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0 or len(samples) < 2:
        raise ValueError("Contact windows need a side, positive FPS and at least two samples")
    runs, current = [], []
    for index, sample in enumerate(samples):
        first, last = max(0, index - 1), min(len(samples) - 1, index + 1)
        speed = abs(samples[last]["feet"][side]["centroid"][2] -
                    samples[first]["feet"][side]["centroid"][2]) * fps / (samples[last]["frame"]-samples[first]["frame"])
        if CONTACT_BAND[0] <= sample["feet"][side]["min_z"] <= CONTACT_BAND[1] and speed <= MAX_VERTICAL_SPEED:
            current.append(index)
        else:
            if current: runs.append(current)
            current = []
    if current: runs.append(current)
    return tuple(run for run in runs if (samples[run[-1]]["frame"]-samples[run[0]]["frame"]) / fps >= MIN_WINDOW_SECONDS)


def contact_envelope(index, runs, fps):
    """Full strength inside a window; smooth halo outside it. Nearest wins.

    A tie chooses the earlier window deterministically. Missing windows never
    activate IK, and separated halos do not join windows into one stance.
    """
    candidates = [(max(run[0] - index, index - run[-1], 0), run[0], run) for run in runs]
    if not candidates:
        return None, 0.
    distance, _, run = min(candidates)
    t = max(0., 1. - distance / (BLEND_SECONDS * fps))
    return (run if t > 0 else None), t * t * (3 - 2 * t)


def blended_contacts(index, runs, fps):
    """Crossfade adjacent halos continuously; full source windows stay exact."""
    inside = next((run for run in runs if run[0] <= index <= run[-1]), None)
    if inside is not None: return ((inside, 1.),), 1.
    radius = BLEND_SECONDS * fps
    active = [(run, contact_envelope(index,(run,),fps)[1]) for run in runs
              if min(abs(index-run[0]),abs(index-run[-1])) < radius]
    if not active: return (), 0.
    if len(active) == 1: return ((active[0][0],1.),), active[0][1]
    earlier = [item for item in active if item[0][-1] < index]
    later = [item for item in active if item[0][0] > index]
    if not earlier or not later:
        run,strength = max(active,key=lambda item:item[1])
        return ((run,1.),), strength
    previous = max(earlier,key=lambda item:item[0][-1])
    following = min(later,key=lambda item:item[0][0])
    low = max(previous[0][-1], following[0][0]-radius)
    high = min(following[0][0], previous[0][-1]+radius)
    t = (index-low)/(high-low)
    weight = t*t*(3-2*t)
    return ((previous[0],1-weight),(following[0],weight)), previous[1]*(1-weight)+following[1]*weight
