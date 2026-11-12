"""Strict, bounded JSON adapters to the existing immutable engine contracts."""
from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import fields

from .core.diagnostic_contracts import Region, ViewSetRevision
from .core.diagnostics_preflight import AlignmentAnchor, RasterInput, ViewInput
from .errors import EngineError

MAX_REQUEST_BYTES = 67_108_864
MAX_TOTAL_PIXELS = 4_194_304
MAX_PNG_BYTES = 33_554_432


def object_fields(value, allowed, required=(), *, name="arguments"):
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ValueError(f"{name} must be a JSON object.")
    if set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(f"{name} has unsupported or missing fields.")
    return value


def validate_json(value) -> None:
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if depth > 40 or nodes > 20_000_000:
            raise ValueError("Engine arguments exceed the JSON structure budget.")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise ValueError("Engine arguments must contain only finite JSON values.")
    visit(value, 0)
    if len(json.dumps(value, allow_nan=False, separators=(",", ":")).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("Engine arguments exceed the 64 MiB encoded request budget.")


def raster(value):
    if type(value) is not dict:
        raise ValueError("A raster must be a JSON object.")
    if "png_base64" in value:
        object_fields(value, ("png_base64", "format"), ("png_base64",), name="PNG raster")
        encoded = value["png_base64"]
        if value.get("format", "png") != "png" or type(encoded) is not str or len(encoded) > (MAX_PNG_BYTES + 2) // 3 * 4:
            raise ValueError("PNG raster has invalid format or exceeds the encoded byte budget.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("PNG raster must use valid base64.") from exc
        if len(raw) > MAX_PNG_BYTES:
            raise ValueError("PNG raster exceeds the 32 MiB byte budget.")
        return RasterInput.from_png_bytes(raw)
    object_fields(value, ("width", "height", "rgba", "format"), ("width", "height", "rgba"), name="RGBA raster")
    width, height, rgba = value["width"], value["height"], value["rgba"]
    if (value.get("format", "rgba") != "rgba" or type(width) is not int or type(height) is not int
            or width <= 0 or height <= 0 or width * height > 1_048_576
            or type(rgba) is not list or len(rgba) != width * height * 4
            or any(type(channel) not in (int, float) or not math.isfinite(channel) or not 0 <= channel <= 1 for channel in rgba)):
        raise ValueError("RGBA raster requires positive bounded dimensions and finite normalized flat RGBA.")
    return RasterInput.from_pixels(width, height, rgba)


def policy(model, value):
    value = {} if value is None else value
    object_fields(value, (field.name for field in fields(model)), name="policy")
    # Do not let dataclass policies silently coerce JSON booleans to numbers.
    for field in fields(model):
        if field.name in value:
            default = field.default
            if type(default) in (int, float) and type(value[field.name]) not in (int, float):
                raise ValueError(f"Policy {field.name} requires a number.")
    return model(**value)


def view_arguments(arguments, *, preflight=False, extra_fields=()):
    allowed = ("view_set", "inputs", "policy", "regions") + (("anchors",) if preflight else ()) + tuple(extra_fields)
    object_fields(arguments, allowed, ("view_set", "inputs"))
    revision = ViewSetRevision.from_dict(arguments["view_set"])
    if len(revision.views) > 20:
        raise ValueError("At most 20 views fit the engine request profile.")
    supplied = arguments["inputs"]
    if type(supplied) is not dict or not set(supplied) <= {v.view_id for v in revision.views}:
        raise ValueError("Inputs must be keyed by declared view IDs.")
    decoded, pixels = {}, 0
    for name, data in supplied.items():
        object_fields(data, ("image", "mask"), ("image",), name="view input")
        image = raster(data["image"])
        mask = raster(data["mask"]) if data.get("mask") is not None else None
        for item in (image, mask):
            if item is not None and item.width is not None and item.height is not None:
                pixels += item.width * item.height
                if pixels > MAX_TOTAL_PIXELS:
                    raise ValueError("Decoded rasters exceed the aggregate 4 Mi-pixel request budget.")
        decoded[name] = ViewInput(image, mask)
    region_data = arguments.get("regions", [])
    if type(region_data) is not list or len(region_data) > 128:
        raise ValueError("At most 128 explicit image regions are supported.")
    regions = tuple(Region.from_dict(item) for item in region_data)
    anchors = []
    if preflight:
        anchor_data = arguments.get("anchors", [])
        if type(anchor_data) is not list or len(anchor_data) > 20:
            raise ValueError("At most 20 independent preflight anchors are supported.")
        for item in anchor_data:
            object_fields(item, ("target_view_id", "reference_view_id", "evidence_sha256"),
                          ("target_view_id", "reference_view_id", "evidence_sha256"), name="alignment anchor")
            if any(type(v) is not str for v in item.values()):
                raise ValueError("Alignment anchor values must be strings.")
            anchors.append(AlignmentAnchor(**item))
    return revision, decoded, regions, tuple(anchors)


def appearance_arguments(arguments):
    """Decode D4 JSON through the same core authority as direct/Blender callers."""
    from .core.appearance_diagnostics import AppearancePolicy, AppearanceRegionAnchor, AppearanceViewSettings, SurfaceMesh
    from .core.diagnostic_contracts import DiagnosticReport
    revision, inputs, regions, _ = view_arguments(arguments,
        extra_fields=("surface", "view_settings", "region_anchors", "upstream_reports"))
    raw_settings = arguments.get("view_settings", {})
    if type(raw_settings) is not dict or not set(raw_settings) <= {view.view_id for view in revision.views}:
        raise ValueError("Appearance settings must be keyed by current source view IDs.")
    settings = {name: AppearanceViewSettings.from_dict(value) for name, value in raw_settings.items()}
    raw_anchors = arguments.get("region_anchors", [])
    raw_reports = arguments.get("upstream_reports", [])
    if type(raw_anchors) is not list or len(raw_anchors) > 128 or type(raw_reports) is not list or len(raw_reports) > 20:
        raise ValueError("Appearance anchor/upstream report counts exceed the declared profile.")
    anchors = tuple(AppearanceRegionAnchor.from_dict(value) for value in raw_anchors)
    reports = tuple(DiagnosticReport.from_dict(value) for value in raw_reports)
    surface = SurfaceMesh.from_dict(arguments["surface"]) if arguments.get("surface") is not None else None
    return revision, inputs, surface, settings, regions, anchors, reports, policy(AppearancePolicy, arguments.get("policy"))
