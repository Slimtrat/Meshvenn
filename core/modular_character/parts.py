"""Immutable anatomical-region and bone-relative socket declarations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .validation import fields, identifier, sequence, text, vector


@dataclass(frozen=True)
class RegionSpec:
    id: str
    role: str
    node_name: str

    def __post_init__(self):
        identifier(self.id, name="region id")
        identifier(self.role, name="region role")
        text(self.node_name, name="region node_name")

    @classmethod
    def from_dict(cls, value):
        fields(value, ("id", "role", "node_name"), name="region")
        return cls(**value)

    def to_dict(self):
        return {"id": self.id, "role": self.role, "node_name": self.node_name}


@dataclass(frozen=True)
class SocketSpec:
    id: str
    role: str
    parent_bone: str
    region_id: str
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: tuple[float, float, float]
    frame: str = "gltf-joint-local"
    units: str = "meters"

    def __post_init__(self):
        identifier(self.id, name="socket id")
        identifier(self.role, name="socket role")
        text(self.parent_bone, name="socket parent_bone")
        identifier(self.region_id, name="socket region_id")
        if self.frame != "gltf-joint-local" or self.units != "meters":
            raise ValueError("Socket v1 requires a gltf-joint-local transform in meters.")
        object.__setattr__(self, "translation", vector(self.translation, 3, name="socket translation"))
        object.__setattr__(self, "rotation", vector(self.rotation, 4, name="socket quaternion (x,y,z,w)"))
        object.__setattr__(self, "scale", vector(self.scale, 3, name="socket scale", positive=True))
        if not math.isclose(sum(value * value for value in self.rotation), 1.0,
                            rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("Socket rotation must be an explicitly normalized quaternion (x,y,z,w).")

    @classmethod
    def from_dict(cls, value):
        fields(value, ("id", "role", "parent_bone", "region_id", "translation", "rotation",
                       "scale", "frame", "units"), name="socket")
        return cls(**value)

    def to_dict(self):
        return {"id": self.id, "role": self.role, "parent_bone": self.parent_bone,
                "region_id": self.region_id, "translation": list(self.translation),
                "rotation": list(self.rotation), "scale": list(self.scale),
                "frame": self.frame, "units": self.units}


@dataclass(frozen=True)
class SeamDeclarations:
    boundary_policy: str = "open-shared-vertices"
    authoring_changes: tuple = ()
    caps: tuple = ()

    def __post_init__(self):
        if self.boundary_policy != "open-shared-vertices":
            raise ValueError("Modular v1 supports only declared open-shared-vertices boundaries.")
        object.__setattr__(self, "authoring_changes", sequence(self.authoring_changes, name="authoring_changes"))
        object.__setattr__(self, "caps", sequence(self.caps, name="caps"))
        if self.authoring_changes or self.caps:
            raise ValueError("Modular v1 cannot publish unvalidated authoring changes or seam caps.")

    @classmethod
    def from_dict(cls, value):
        fields(value, ("boundary_policy", "authoring_changes", "caps"), name="seams")
        return cls(**value)

    def to_dict(self):
        return {"boundary_policy": self.boundary_policy, "authoring_changes": [], "caps": []}
