"""Typed outputs shared by the source-preservation Geometry/Rig/Motion stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ...core.geometry_contracts import GeometrySurfaceOutput


@dataclass(frozen=True)
class PreservedGLBGeometryOutput(GeometrySurfaceOutput):
    armature_object: Any = None
    actions: tuple[Any, ...] = ()
    source_profile_id: str = ""
    source_profile_certification: str = ""
    source_rig_archetype: str = ""
    semantic_bones: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.armature_object is None:
            raise ValueError("Preserved GLB geometry requires its source armature.")
        profile_id = str(self.source_profile_id).strip()
        certification = str(self.source_profile_certification).strip()
        archetype = str(self.source_rig_archetype).strip()
        if not profile_id or not certification or not archetype:
            raise ValueError("Preserved GLB geometry requires source rig identity.")
        semantics = {
            str(role).strip(): str(name).strip()
            for role, name in self.semantic_bones.items()
        }
        if "root" not in semantics or any(
            not role or not name for role, name in semantics.items()
        ):
            raise ValueError("Preserved GLB geometry requires source bone semantics.")
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "source_profile_id", profile_id)
        object.__setattr__(self, "source_profile_certification", certification)
        object.__setattr__(self, "source_rig_archetype", archetype)
        object.__setattr__(self, "semantic_bones", semantics)


def require_preserved_geometry(value: Any) -> PreservedGLBGeometryOutput:
    if not isinstance(value, PreservedGLBGeometryOutput):
        raise TypeError(
            "Source rig preservation requires PreservedGLBGeometryOutput."
        )
    return value


__all__ = ("PreservedGLBGeometryOutput", "require_preserved_geometry")
