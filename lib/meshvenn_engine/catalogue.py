"""Provider-neutral action schemas; semantic validation remains in core models."""
from __future__ import annotations

import types
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from typing import Union, get_args, get_origin, get_type_hints

from .core.diagnostic_contracts import DiagnosticReport, Region, ViewSetRevision
from .core.diagnostics_preflight import AlignmentAnchor, PreflightPolicy
from .core.geometry_diagnostics import GeometryPolicy, VolumeArtifact

VERSION = "0.1.0"


def model_schema(model):
    hints = get_type_hints(model)
    properties = {field.name: type_schema(hints[field.name]) for field in fields(model)}
    required = [field.name for field in fields(model)
                if field.name == "schema_version" or field.default is MISSING and field.default_factory is MISSING]
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def type_schema(annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        return {"anyOf": [type_schema(item) for item in args]}
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": type_schema(args[0])}
        return {"type": "array", "prefixItems": [type_schema(item) for item in args],
                "minItems": len(args), "maxItems": len(args)}
    if is_dataclass(annotation):
        return model_schema(annotation)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {"type": "string", "enum": [item.value for item in annotation]}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}[annotation]}


def _object(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def action_schemas():
    from .core.appearance_diagnostics import AppearancePolicy, AppearanceRegionAnchor, AppearanceViewSettings, SurfaceMesh
    png = _object({"png_base64": {"type": "string", "maxLength": 44_739_244},
                   "format": {"const": "png"}}, ("png_base64",))
    rgba = _object({"format": {"const": "rgba"}, "width": {"type": "integer", "minimum": 1, "maximum": 1_048_576},
        "height": {"type": "integer", "minimum": 1, "maximum": 1_048_576},
        "rgba": {"type": "array", "maxItems": 4_194_304, "items": {"type": "number", "minimum": 0, "maximum": 1}}},
        ("width", "height", "rgba"))
    raster = {"oneOf": [png, rgba]}
    common = {"view_set": model_schema(ViewSetRevision),
        "inputs": {"type": "object", "maxProperties": 20, "additionalProperties": _object(
            {"image": raster, "mask": {"anyOf": [raster, {"type": "null"}]}}, ("image",))},
        "regions": {"type": "array", "maxItems": 128, "items": model_schema(Region)}}
    preflight = _object({**{key: value for key, value in common.items() if key != "regions"}, "policy": model_schema(PreflightPolicy),
        "anchors": {"type": "array", "maxItems": 20, "items": model_schema(AlignmentAnchor)}}, ("view_set", "inputs"))
    diagnosis = _object({**common, "policy": model_schema(GeometryPolicy)}, ("view_set", "inputs"))
    mesh = _object({"volume": model_schema(VolumeArtifact),
        "voxel_size": {"type": "number", "exclusiveMinimum": 0, "maximum": 1_000_000},
        "center_xy": {"type": "boolean"}, "mesh_mode": {"enum": ["blocks", "surface-nets"]},
        "max_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 120}}, ("volume",))
    appearance = _object({**common, "policy": model_schema(AppearancePolicy),
        "surface": {"anyOf": [model_schema(SurfaceMesh), {"type": "null"}]},
        "view_settings": {"type": "object", "maxProperties": 20,
                          "additionalProperties": model_schema(AppearanceViewSettings)},
        "region_anchors": {"type": "array", "maxItems": 128, "items": model_schema(AppearanceRegionAnchor)},
        "upstream_reports": {"type": "array", "maxItems": 20, "items": model_schema(DiagnosticReport)}}, ("view_set", "inputs"))
    output = {"type": "object", "properties": {"schema_version": {"const": 1},
        "verification_status": {"enum": ["pass", "fail", "unknown", "not_applicable"]}},
        "required": ["schema_version", "verification_status"]}
    appearance_output = {"type": "object", "properties": {**output["properties"],
        "identity_status": {"enum": ["pass", "fail", "unknown", "not_applicable"]},
        "deterministic_status": {"enum": ["pass", "fail", "unknown", "not_applicable"]}},
        "required": ["schema_version", "verification_status", "identity_status", "deterministic_status"]}
    return {"engine.capabilities": (_object({}), {"type": "object"}),
            "views.preflight": (preflight, output), "geometry.diagnose": (diagnosis, output),
            "geometry.mesh": (mesh, output), "appearance.diagnose": (appearance, appearance_output)}
