"""Pure, bounded silhouette measurements; no attribution or reconstruction policy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from ..diagnostic_contracts import Region, VerificationStatus
from ..image_mask import BinaryMask
from .projection import DEFAULT_MAX_WORK, _raster_size, check_budget


@dataclass(frozen=True)
class ResidualRegion:
    pixel_count: int
    bounds: tuple[float, float, float, float]

    def to_dict(self) -> dict:
        return {"pixel_count": self.pixel_count, "bounds": list(self.bounds)}

    @classmethod
    def from_dict(cls, data: dict) -> ResidualRegion:
        return cls(data["pixel_count"], tuple(data["bounds"]))


@dataclass(frozen=True)
class RegionComparison:
    region: Region
    status: VerificationStatus
    reason: str
    expected_pixels: int
    missing_pixels: int
    beyond_tolerance_pixels: int
    recall: float | None

    def to_dict(self) -> dict:
        return {"region": self.region.to_dict(), "status": self.status.value,
                "reason": self.reason, "expected_pixels": self.expected_pixels,
                "missing_pixels": self.missing_pixels,
                "beyond_tolerance_pixels": self.beyond_tolerance_pixels, "recall": self.recall}

    @classmethod
    def from_dict(cls, data: dict) -> RegionComparison:
        return cls(Region.from_dict(data["region"]), VerificationStatus(data["status"]),
                   data["reason"], data["expected_pixels"], data["missing_pixels"],
                   data["beyond_tolerance_pixels"], data["recall"])


@dataclass(frozen=True)
class MaskComparison:
    iou: float
    precision: float
    recall: float
    expected_pixels: int
    actual_pixels: int
    intersection_pixels: int
    missing_pixels: int
    extraneous_pixels: int
    missing_beyond_tolerance_pixels: int
    extraneous_beyond_tolerance_pixels: int
    missing_mask: BinaryMask
    extraneous_mask: BinaryMask
    contour_mean_pixels: float | None
    contour_max_pixels: float | None
    missing_regions: tuple[ResidualRegion, ...]
    extraneous_regions: tuple[ResidualRegion, ...]
    missing_region_count: int
    extraneous_region_count: int
    important_regions: tuple[RegionComparison, ...]
    components: tuple[RegionComparison, ...]
    component_count: int
    components_truncated: bool

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        for key in ("missing_mask", "extraneous_mask"):
            mask = data[key]
            data[key] = {"width": mask.width, "height": mask.height,
                         "values_hex": mask.values.hex()}
        for key in ("missing_regions", "extraneous_regions", "important_regions", "components"):
            data[key] = [item.to_dict() for item in data[key]]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> MaskComparison:
        data = dict(data)
        for key in ("missing_mask", "extraneous_mask"):
            mask = data[key]
            data[key] = BinaryMask(mask["width"], mask["height"], bytes.fromhex(mask["values_hex"]))
        for key in ("missing_regions", "extraneous_regions"):
            data[key] = tuple(ResidualRegion.from_dict(item) for item in data[key])
        for key in ("important_regions", "components"):
            data[key] = tuple(RegionComparison.from_dict(item) for item in data[key])
        return cls(**data)


def _edt_line(values: list[float]) -> list[float]:
    """Exact squared Euclidean distance transform via a parabola envelope."""
    sites = [index for index, value in enumerate(values) if math.isfinite(value)]
    if not sites:
        return [math.inf] * len(values)
    vertices = [sites[0]]
    breaks = [-math.inf, math.inf]
    for site in sites[1:]:
        while True:
            previous = vertices[-1]
            crossing = ((values[site] + site * site) -
                        (values[previous] + previous * previous)) / (2 * (site - previous))
            if crossing > breaks[-2]:
                break
            vertices.pop()
            breaks.pop(-2)
        vertices.append(site)
        breaks.insert(-1, crossing)
    result = []
    current = 0
    for index in range(len(values)):
        while breaks[current + 1] < index:
            current += 1
        site = vertices[current]
        result.append((index - site) ** 2 + values[site])
    return result


def _distance_squared(values: bytes, width: int, height: int, deadline, cancel) -> list[float]:
    distances = [math.inf] * len(values)
    for y in range(height):
        check_budget(deadline, cancel)
        row = y * width
        distances[row:row + width] = _edt_line(
            [0.0 if value else math.inf for value in values[row:row + width]])
    for x in range(width):
        check_budget(deadline, cancel)
        column = _edt_line([distances[y * width + x] for y in range(height)])
        for y, value in enumerate(column):
            distances[y * width + x] = value
    return distances


def _contour(values: bytes, width: int, height: int) -> bytes:
    result = bytearray(len(values))
    for index, value in enumerate(values):
        if value:
            y, x = divmod(index, width)
            if (x == 0 or y == 0 or x == width - 1 or y == height - 1
                    or not values[index - 1] or not values[index + 1]
                    or not values[index - width] or not values[index + width]):
                result[index] = 1
    return bytes(result)


def _components(values: bytes, width: int, height: int, deadline, cancel):
    """Yield deterministic four-connected components with O(raster) storage."""
    seen = bytearray(len(values))
    for seed, value in enumerate(values):
        if seed % 1024 == 0:
            check_budget(deadline, cancel)
        if not value or seen[seed]:
            continue
        seen[seed] = 1
        component = [seed]
        position = 0
        while position < len(component):
            if position % 1024 == 0:
                check_budget(deadline, cancel)
            index = component[position]
            y, x = divmod(index, width)
            for neighbor, valid in ((index - 1, x > 0), (index + 1, x + 1 < width),
                                    (index - width, y > 0), (index + width, y + 1 < height)):
                if valid and values[neighbor] and not seen[neighbor]:
                    seen[neighbor] = 1
                    component.append(neighbor)
            position += 1
        yield component


def _bounds(indices: Sequence[int], width: int, height: int):
    xs = [index % width for index in indices]
    ys = [index // width for index in indices]
    left, right, bottom, top = min(xs), max(xs), min(ys), max(ys)
    normalized = (max(0, (left - 0.5) / (width - 1)) if width > 1 else 0.0,
                  max(0, (bottom - 0.5) / (height - 1)) if height > 1 else 0.0,
                  min(1, (right + 0.5) / (width - 1)) if width > 1 else 1.0,
                  min(1, (top + 0.5) / (height - 1)) if height > 1 else 1.0)
    return normalized, (right - left + 1, top - bottom + 1)


def _region_result(region, indices, actual, distances, width, height, min_pixels,
                   min_extent, tolerance, min_recall):
    count = len(indices)
    missing = sum(not actual[index] for index in indices)
    beyond = sum(distances[index] > tolerance * tolerance + 1e-9 for index in indices)
    recall = (count - missing) / count if count else None
    if region.bounds is None:
        status, reason = VerificationStatus.UNKNOWN, "Region has no declared image bounds."
    elif not count:
        status, reason = VerificationStatus.UNKNOWN, "Region contains no expected foreground samples."
    elif count < min_pixels or min(_bounds(indices, width, height)[1]) < min_extent + 2 * tolerance:
        status, reason = VerificationStatus.UNKNOWN, "Region is smaller than the diagnostic resolution."
    elif recall < min_recall:
        if beyond:
            status, reason = VerificationStatus.FAIL, "Expected region has missing coverage beyond resolution tolerance."
        else:
            status, reason = VerificationStatus.UNKNOWN, "Region deficit lies within resolution tolerance."
    else:
        status, reason = VerificationStatus.PASS, "Expected region recall meets the declared threshold."
    return RegionComparison(region, status, reason, count, missing, beyond, recall)


def compare_masks(expected: BinaryMask, actual: BinaryMask, *, regions: Sequence[Region] = (),
                  min_region_pixels: int = 4, min_region_extent_pixels: float = 2.0,
                  resolution_tolerance_pixels: float = 0.0, min_region_recall: float = 0.95,
                  max_regions: int = 128, max_work: int = DEFAULT_MAX_WORK,
                  deadline: float | None = None,
                  cancel: Callable[[], bool] | None = None) -> MaskComparison:
    """Measure same-grid silhouettes with exact Euclidean contour distances.

    Pixel contours use four-neighbour foreground boundaries. Symmetric mean is
    weighted by contour sample count; maximum is symmetric Hausdorff distance.
    An empty/nonempty contour comparison is undefined (None), never a zero.
    Components and supplied regions are assessed separately from global IoU.
    """
    width, height = expected.width, expected.height
    _raster_size(width, height)
    check_budget(deadline, cancel)
    if (width, height) != (actual.width, actual.height):
        raise ValueError("Mask comparisons require the same raster dimensions.")
    if (type(max_work) is not int or max_work <= 0 or type(max_regions) is not int
            or not 1 <= max_regions <= 1024 or type(min_region_pixels) is not int
            or min_region_pixels <= 0):
        raise ValueError("Metric budgets and minimum pixel counts must be positive bounded integers.")
    if (not math.isfinite(resolution_tolerance_pixels) or resolution_tolerance_pixels < 0
            or not math.isfinite(min_region_extent_pixels) or min_region_extent_pixels <= 0
            or not math.isfinite(min_region_recall) or not 0 <= min_region_recall <= 1):
        raise ValueError("Region thresholds and resolution tolerance must be finite and valid.")
    if len(regions) > max_regions or (32 + len(regions)) * width * height > max_work:
        raise ValueError("Diagnostic metric work budget exceeded.")
    e = bytes(bool(value) for value in expected.values)
    a = bytes(bool(value) for value in actual.values)
    missing = bytes(ev and not av for ev, av in zip(e, a))
    excess = bytes(av and not ev for ev, av in zip(e, a))
    expected_count, actual_count = sum(e), sum(a)
    missing_count, excess_count = sum(missing), sum(excess)
    intersection = expected_count - missing_count
    union = expected_count + excess_count
    a_dist = _distance_squared(a, width, height, deadline, cancel)
    e_dist = _distance_squared(e, width, height, deadline, cancel)
    tolerance_squared = resolution_tolerance_pixels ** 2 + 1e-9
    missing_beyond = sum(value and a_dist[index] > tolerance_squared for index, value in enumerate(missing))
    excess_beyond = sum(value and e_dist[index] > tolerance_squared for index, value in enumerate(excess))
    e_contour, a_contour = _contour(e, width, height), _contour(a, width, height)
    if not any(e_contour) and not any(a_contour):
        contour_mean = contour_max = 0.0
    elif not any(e_contour) or not any(a_contour):
        contour_mean = contour_max = None
    else:
        ac_dist = _distance_squared(a_contour, width, height, deadline, cancel)
        ec_dist = _distance_squared(e_contour, width, height, deadline, cancel)
        distances = ([math.sqrt(ac_dist[index]) for index, value in enumerate(e_contour) if value]
                     + [math.sqrt(ec_dist[index]) for index, value in enumerate(a_contour) if value])
        contour_mean, contour_max = sum(distances) / len(distances), max(distances)
    residuals = []
    counts = []
    for values in (missing, excess):
        items = [ResidualRegion(len(indices), _bounds(indices, width, height)[0])
                 for indices in _components(values, width, height, deadline, cancel)]
        counts.append(len(items))
        residuals.append(tuple(sorted(items, key=lambda item: (-item.pixel_count, item.bounds))[:max_regions]))
    component_results = []
    component_count = 0
    for component_count, indices in enumerate(_components(e, width, height, deadline, cancel), 1):
        if len(component_results) < max_regions:
            region = Region("diagnostic", f"component-{component_count}", _bounds(indices, width, height)[0])
            component_results.append(_region_result(region, indices, a, a_dist, width, height,
                min_region_pixels, min_region_extent_pixels, resolution_tolerance_pixels, min_region_recall))
    region_results = []
    for region in regions:
        check_budget(deadline, cancel)
        if region.bounds is None:
            indices = []
        else:
            left, bottom, right, top = region.bounds
            indices = [index for index, value in enumerate(e) if value
                       and left <= ((index % width) / (width - 1) if width > 1 else 0.5) <= right
                       and bottom <= ((index // width) / (height - 1) if height > 1 else 0.5) <= top]
        region_results.append(_region_result(region, indices, a, a_dist, width, height,
            min_region_pixels, min_region_extent_pixels, resolution_tolerance_pixels, min_region_recall))
    check_budget(deadline, cancel)
    return MaskComparison(intersection / union if union else 1.0,
        intersection / actual_count if actual_count else (1.0 if not expected_count else 0.0),
        intersection / expected_count if expected_count else 1.0,
        expected_count, actual_count, intersection, missing_count, excess_count,
        missing_beyond, excess_beyond, BinaryMask(width, height, missing), BinaryMask(width, height, excess),
        contour_mean, contour_max, residuals[0], residuals[1], counts[0], counts[1],
        tuple(region_results), tuple(component_results), component_count, component_count > max_regions)
