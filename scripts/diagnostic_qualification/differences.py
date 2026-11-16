"""A\\B and B\\A on one fixed image grid; signed subtraction never cancels defects."""
from __future__ import annotations


def unavailable(reason: str) -> dict:
    return {"schema_version": 1, "status": "unknown", "reason": reason,
            "before_minus_after": {"outside_edit_mask_pixels": None, "outside_edit_mask_empty": None},
            "after_minus_before": {"outside_edit_mask_pixels": None, "outside_edit_mask_empty": None},
            "outside_edit_mask": {"foreground_symmetric_difference_pixels": None,
                                  "foreground_difference_empty": None, "changed_rgba_pixels": None,
                                  "rgba_difference_empty": None, "status": "unknown"}}


def directional_differences(before, after, support: bytes, width: int, height: int) -> dict:
    count = width * height
    if width < 1 or height < 1 or len(before) != count * 4 or len(after) != count * 4 or len(support) != count:
        raise ValueError("Directional differences require the same complete image grid and edit mask.")
    removed = added = changed = removed_outside = added_outside = changed_outside = 0
    removed_map, added_map = bytearray(), bytearray()
    for pixel in range(count):
        i = pixel * 4
        editable = bool(support[pixel])
        old_foreground, new_foreground = before[i+3] >= .5, after[i+3] >= .5
        lost, gained = old_foreground and not new_foreground, new_foreground and not old_foreground
        different = before[i:i+4] != after[i:i+4]
        removed += lost
        added += gained
        changed += different
        removed_outside += lost and not editable
        added_outside += gained and not editable
        changed_outside += different and not editable
        neutral = (35, 145, 100, 255) if editable else (238, 241, 245, 255)
        removed_map.extend((210, 45, 65, 255) if lost and not editable else neutral)
        added_map.extend((45, 95, 210, 255) if gained and not editable else neutral)
    return {
        "schema_version": 1, "status": "measured", "comparison": "before_vs_after",
        "definition": "Foreground sets contain (x,y) where alpha >= .5; RGBA sets contain (x,y,R,G,B,A). No resampling or alignment.",
        "before_minus_after": {"foreground_pixels": removed, "outside_edit_mask_pixels": removed_outside,
                               "outside_edit_mask_empty": removed_outside == 0},
        "after_minus_before": {"foreground_pixels": added, "outside_edit_mask_pixels": added_outside,
                               "outside_edit_mask_empty": added_outside == 0},
        "full_image": {"foreground_symmetric_difference_pixels": removed + added,
                       "foreground_difference_empty": removed + added == 0, "changed_rgba_pixels": changed,
                       "rgba_difference_empty": changed == 0},
        "outside_edit_mask": {
            "foreground_symmetric_difference_pixels": removed_outside + added_outside,
            "foreground_difference_empty": removed_outside + added_outside == 0,
            "rgba_before_minus_after_samples": changed_outside,
            "rgba_after_minus_before_samples": changed_outside,
            "rgba_symmetric_difference_samples": 2 * changed_outside,
            "changed_rgba_pixels": changed_outside, "rgba_difference_empty": changed_outside == 0,
            "status": "pass" if changed_outside == 0 else "fail"},
        "before_minus_after_rgba": bytes(removed_map), "after_minus_before_rgba": bytes(added_map),
    }
