"""Provider-neutral action schemas; semantic validation remains in core models."""
from __future__ import annotations

import types
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from typing import Union, get_args, get_origin, get_type_hints

from .core.diagnostic_contracts import DiagnosticReport, Region, ViewSetRevision
from .core.diagnostics_preflight import AlignmentAnchor, PreflightPolicy
from .core.geometry_diagnostics import GeometryPolicy, VolumeArtifact
from .dto import LOOP_OPERATIONS

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
    from .core.correction_plans import CorrectionPlan, CorrectionPolicy, CorrectionResult, EditAnnotation, PreparedCorrection, ProviderCapabilities
    from .loop_runtime import loop_payload_schemas
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
    correction = _object({"view_set": model_schema(ViewSetRevision),
        "reports": {"type": "array", "maxItems": 20, "items": model_schema(DiagnosticReport)},
        "capabilities": model_schema(ProviderCapabilities),
        "annotations": {"type": "array", "maxItems": 128, "items": model_schema(EditAnnotation)},
        "policy": model_schema(CorrectionPolicy)}, ("view_set", "reports"))
    prepare = _object({**correction["properties"], "plan": model_schema(CorrectionPlan)}, ("plan", "view_set", "reports"))
    loop = _object({"operation": {"enum": list(LOOP_OPERATIONS)},
        "session_id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$", "maxLength": 128},
        "payload": {"type": "object"}}, ("operation", "session_id"))
    payload_schemas = loop_payload_schemas()
    if set(payload_schemas) != set(LOOP_OPERATIONS):
        raise RuntimeError("Loop runtime and action catalogue disagree on supported operations.")
    loop["oneOf"] = [{"properties": {"operation": {"const": operation}, "payload": schema},
                      "required": ["payload"] if schema.get("required") else []}
                     for operation, schema in payload_schemas.items()]
    def correction_output(model):
        schema = model_schema(model)
        schema["properties"]["verification_status"] = {"const": "unknown"}
        schema["required"].append("verification_status")
        return schema
    return {"engine.capabilities": (_object({}), {"type": "object"}),
            "views.preflight": (preflight, output), "geometry.diagnose": (diagnosis, output),
            "geometry.mesh": (mesh, output), "appearance.diagnose": (appearance, appearance_output),
            "corrections.plan": (correction, correction_output(CorrectionResult)),
            "corrections.prepare": (prepare, correction_output(PreparedCorrection)),
            "corrections.loop": (loop, {"type": "object", "properties": {"schema_version": {"const": 1},
                "verification_status": {"const": "unknown"}, "session_id": loop["properties"]["session_id"],
                "status": {"type": "string"}, "known_cost": {"type": "number", "minimum": 0},
                "cost_uncertain": {"type": "boolean"}},
                "required": ["schema_version", "verification_status"]})}
