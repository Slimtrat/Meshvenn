"""Explicit source authority for a generated native head; no image repainting."""

from dataclasses import replace
import math


def coherent_head_views(mesh, views, space, mask_type):
    group = mesh.vertex_groups.get("head")
    if group is None:
        raise ValueError("Head source policy requires an explicit head region")
    points = [
        v.co.z
        for v in mesh.data.vertices
        if any(g.group == group.index and g.weight > 0.8 for g in v.groups)
    ]
    if len(points) < 16:
        raise ValueError("Insufficient native head ownership")
    cutoff = min(points) / (space.height * space.voxel_size)
    if not 0.5 < cutoff < 0.95:
        raise ValueError("Head region outside the saved native projection frame")
    allowed = []
    masked = []
    result = []
    removed = 0
    for view in views:
        if abs(view.transform.elevation_degrees) > 1e-7:
            raise ValueError("Head source policy requires level source cameras")
        angle = view.transform.azimuth_degrees % 360
        if min(abs(angle), abs(angle - 180), abs(angle - 360)) < 1e-7:
            result.append(view)
            allowed.append(view.name)
            continue
        width, height = view.image.width, view.image.height
        values = bytearray(
            view.mask.values if view.mask is not None else bytes([1]) * (width * height)
        )
        # Keep lateral cloth observations. Only contradictory dark facial
        # details are reserved for front/back sources, avoiding a head-wide
        # flat-color band when the two remaining cameras become grazing.
        radius = max(1, round(6 * height / 627))
        reject = set()
        for y in range(math.ceil(cutoff * (height - 1)), height):
            for x in range(width):
                color = view.image.sample_bilinear_alpha_aware(
                    x / max(1, width - 1), y / max(1, height - 1)
                )
                if color[3] < 0.5 or max(color[:3]) >= 0.22:
                    continue
                for yy in range(
                    max(math.ceil(cutoff * (height - 1)), y - radius),
                    min(height, y + radius + 1),
                ):
                    for xx in range(max(0, x - radius), min(width, x + radius + 1)):
                        reject.add(yy * width + xx)
        removed += sum(values[i] for i in reject)
        for i in reject:
            values[i] = 0
        result.append(replace(view, mask=mask_type(width, height, bytes(values))))
        masked.append(view.name)
    orientations = {
        round(v.transform.azimuth_degrees % 360) for v in views if v.name in allowed
    }
    if len(allowed) != 2 or orientations != {0, 180}:
        raise ValueError("Require one front and one back head authority")
    return tuple(result), dict(
        policy="native-head-feature-authority-v1",
        head_cutoff_v=cutoff,
        allowed_head_views=allowed,
        head_masked_views=masked,
        excluded_mask_pixels=removed,
        dark_feature_max_linear_rgb=0.22,
        dilation_pixels_at_627=6,
        scope="Front/back authority for dark generated head markings; lateral cloth retained; source images and geometry unchanged",
    )
