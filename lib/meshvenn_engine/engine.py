"""Application facade over Meshvenn's authoritative deterministic engines."""
from __future__ import annotations

import json
import math
from dataclasses import asdict

from .catalogue import VERSION, action_schemas
from .core.diagnostics_preflight import PreflightPolicy, analyze_preflight
from .core.geometry_diagnostics import GeometryPolicy, NativeGeometryBackend, VolumeArtifact, analyze_geometry
from .dto import object_fields, policy, validate_json, view_arguments
from .errors import EngineError
from .native import NativeRuntime


class MeshvennEngine:
    """A trusted host configures native paths; action arguments only contain data."""

    def __init__(self, native_library=None, python_executable=None):
        self._runtime = NativeRuntime(native_library, python_executable)

    def capabilities(self) -> dict:
        available, reason = self._runtime.availability()
        actions = {}
        for action, (input_schema, output_schema) in action_schemas().items():
            native = action.startswith("geometry.")
            actions[action] = {"version": 1, "available": available if native else True,
                "reason": reason if native else "Deterministic local Python action.",
                "input_schema": input_schema, "output_schema": output_schema}
        return {"schema_version": 1, "engine_version": VERSION, "actions": actions,
            "native": {"configured": available, "expected_abi": 1},
            "limits": {"request_bytes": 67_108_864, "decoded_pixels": 4_194_304,
                       "mesh_vertices": 262_144, "mesh_indices": 1_048_576},
            "scope": ["Deterministic input diagnostics, bounded native geometry diagnostics and native surface extraction.",
                      "Blender pipelines, rigging, animation, appearance identity and export certification are not advertised."]}

    def execute(self, action: str, arguments: dict, *, cancel=None) -> dict:
        if type(action) is not str or action not in action_schemas():
            raise EngineError("unknown_action", "The requested engine action is not supported.")
        try:
            object_fields(arguments, action_schemas()[action][0]["properties"],
                          action_schemas()[action][0].get("required", ()))
            validate_json(arguments)
            if cancel is not None and cancel():
                raise EngineError("cancelled", "Engine execution was cancelled before analysis.")
            if action == "engine.capabilities":
                return self.capabilities()
            if action == "geometry.mesh":
                volume = VolumeArtifact.from_dict(arguments["volume"])
                voxel_size = arguments.get("voxel_size", 1.0)
                duration = arguments.get("max_seconds", 30.0)
                center = arguments.get("center_xy", True)
                mode = arguments.get("mesh_mode", "blocks")
                if (type(voxel_size) not in (int, float) or not math.isfinite(voxel_size) or not 0 < voxel_size <= 1_000_000
                        or type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 120
                        or type(center) is not bool or mode not in ("blocks", "surface-nets")):
                    raise ValueError("Native mesh settings have invalid types or exceed their explicit bounds.")
                return self._runtime.mesh(dict(volume=volume.to_dict(), voxel_size=float(voxel_size),
                    center_xy=center, mesh_mode=mode, max_seconds=float(duration)), cancel=cancel)
            preflight = action == "views.preflight"
            revision, inputs, regions, anchors = view_arguments(arguments, preflight=preflight)
            if preflight:
                if regions:
                    raise ValueError("Preflight has no localized region checks; use geometry.diagnose for regions.")
                result = analyze_preflight(revision, inputs, anchors=anchors,
                                           policy=policy(PreflightPolicy, arguments.get("policy")))
                data = {"schema_version": 1, "report": result.report.to_dict(),
                        "proposals": [asdict(proposal) for proposal in result.proposals]}
            else:
                backend = NativeGeometryBackend(self._runtime.library, python_executable=self._runtime.python)
                result = analyze_geometry(revision, inputs, policy=policy(GeometryPolicy, arguments.get("policy")),
                                          backend=backend, regions=regions, cancel=cancel)
                data = result.to_dict()
            if preflight and cancel is not None and cancel():
                raise EngineError("cancelled", "Engine execution was cancelled before result delivery.")
            data["verification_status"] = result.report.verification_status.value
            # Normalize tuples and enum subclasses at the public JSON boundary.
            return json.loads(json.dumps(data, allow_nan=False, separators=(",", ":")))
        except EngineError:
            raise
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise EngineError("invalid_arguments", str(exc)) from exc
