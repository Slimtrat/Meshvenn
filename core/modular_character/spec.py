"""Versioned, engine-neutral modular character authoring contract."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .coordinates import CoordinateConvention
from .ownership import normalize_hashes, normalize_ownership, validate_ownership, validate_source_surfaces
from .parts import RegionSpec, SeamDeclarations, SocketSpec
from .validation import fields, identifier, integer, sequence, text, unique


CONTRACT_ID = "meshvenn.modular-character"
CONTRACT_VERSION = 1
_CAPABILITY_FIELDS = ("full_body_only", "modular_regions", "supported_socket_ids",
                      "supported_socket_roles", "missing_socket_roles", "ambiguous_socket_roles")


@dataclass(frozen=True)
class ModularCharacterSpec:
    rig_id: str
    rig_version: int
    coordinates: CoordinateConvention
    regions: tuple[RegionSpec, ...]
    ownership: Mapping[str, tuple[str, ...]]
    ownership_source_sha256: Mapping[str, str]
    seams: SeamDeclarations
    sockets: tuple[SocketSpec, ...]
    missing_socket_roles: tuple[str, ...] = ()
    contract: str = CONTRACT_ID
    version: int = CONTRACT_VERSION

    def __post_init__(self):
        if self.contract != CONTRACT_ID or type(self.version) is not int or self.version != CONTRACT_VERSION:
            raise ValueError("Unsupported modular character contract/version.")
        identifier(self.rig_id, name="rig_id")
        integer(self.rig_version, name="rig_version", minimum=1)
        if not isinstance(self.coordinates, CoordinateConvention) or not isinstance(self.seams, SeamDeclarations):
            raise TypeError("Modular spec requires coordinate and seam declarations.")
        regions = sequence(self.regions, name="regions")
        sockets = sequence(self.sockets, name="sockets")
        if not regions or any(not isinstance(region, RegionSpec) for region in regions):
            raise ValueError("Modular spec requires nonempty RegionSpec declarations.")
        if any(not isinstance(socket, SocketSpec) for socket in sockets):
            raise TypeError("Modular sockets must be SocketSpec declarations.")
        unique(tuple(item.id for item in (*regions, *sockets)), name="region/socket ids")
        unique(tuple(item.role for item in regions), name="region roles")
        unique(tuple(item.node_name for item in regions), name="region node names")
        unique(tuple(item.role for item in sockets), name="socket roles")
        ownership = normalize_ownership(self.ownership)
        fingerprints = normalize_hashes(self.ownership_source_sha256, source_names=ownership)
        region_ids = {region.id for region in regions}
        validate_ownership(ownership, region_ids)
        if any(socket.region_id not in region_ids for socket in sockets):
            raise ValueError("A socket references an undeclared owning region.")
        missing = tuple(identifier(role, name="missing socket role")
                        for role in sequence(self.missing_socket_roles, name="missing_socket_roles"))
        unique(missing, name="missing socket roles")
        if set(missing) & {socket.role for socket in sockets}:
            raise ValueError("A supported socket role cannot also be declared missing.")
        for name, value in (("regions", regions), ("sockets", sockets), ("ownership", ownership),
                            ("ownership_source_sha256", fingerprints), ("missing_socket_roles", missing)):
            object.__setattr__(self, name, value)

    @property
    def capabilities(self):
        return {"full_body_only": len(self.regions) == 1, "modular_regions": len(self.regions) > 1,
                "supported_socket_ids": [socket.id for socket in self.sockets],
                "supported_socket_roles": [socket.role for socket in self.sockets],
                "missing_socket_roles": list(self.missing_socket_roles), "ambiguous_socket_roles": []}

    @classmethod
    def from_dict(cls, value):
        fields(value, ("contract", "version", "rig_id", "rig_version", "coordinates", "regions",
                       "ownership", "ownership_source_sha256", "seams", "sockets"),
               optional=("capabilities",), name="modular character spec")
        capability = value.get("capabilities")
        missing = ()
        if "capabilities" in value:
            fields(capability, _CAPABILITY_FIELDS, name="capabilities")
            if any(type(capability[name]) is not bool for name in ("full_body_only", "modular_regions")):
                raise TypeError("Capability flags must be booleans.")
            missing = sequence(capability["missing_socket_roles"], name="missing_socket_roles")
        result = cls(contract=value["contract"], version=value["version"],
                     rig_id=value["rig_id"], rig_version=value["rig_version"],
                     coordinates=CoordinateConvention.from_dict(value["coordinates"]),
                     regions=tuple(RegionSpec.from_dict(item)
                                   for item in sequence(value["regions"], name="regions")),
                     ownership=value["ownership"], ownership_source_sha256=value["ownership_source_sha256"],
                     seams=SeamDeclarations.from_dict(value["seams"]),
                     sockets=tuple(SocketSpec.from_dict(item)
                                   for item in sequence(value["sockets"], name="sockets")),
                     missing_socket_roles=missing)
        if "capabilities" in value and dict(capability) != result.capabilities:
            raise ValueError("Capability declarations do not match actual regions and sockets.")
        return result

    def to_dict(self):
        return {"contract": self.contract, "version": self.version, "rig_id": self.rig_id,
                "rig_version": self.rig_version, "coordinates": self.coordinates.to_dict(),
                "regions": [region.to_dict() for region in self.regions],
                "ownership": {source: list(owners) for source, owners in self.ownership.items()},
                "ownership_source_sha256": dict(self.ownership_source_sha256),
                "seams": self.seams.to_dict(), "sockets": [socket.to_dict() for socket in self.sockets],
                "capabilities": self.capabilities}

    def validate_against(self, mesh_face_counts, bone_names, rig_id, *, mesh_surface_hashes, rig_version=None):
        """Validate exact source coverage, freshness and native skeleton identity."""
        identifier(rig_id, name="source rig_id")
        if rig_version is not None:
            integer(rig_version, name="source rig_version", minimum=1)
        if rig_id != self.rig_id or (rig_version is not None and rig_version != self.rig_version):
            raise ValueError("Modular character rig identity/version does not match the source rig.")
        if isinstance(bone_names, (str, bytes)):
            raise TypeError("bone_names must contain the exact native bone names.")
        bones = tuple(text(name, name="bone name") for name in bone_names)
        if not bones:
            raise ValueError("Modular character requires a nonempty native skeleton.")
        unique(bones, name="native bone names")
        missing = {socket.parent_bone for socket in self.sockets} - set(bones)
        if missing:
            raise ValueError(f"Sockets reference missing native bones: {sorted(missing)}.")
        validate_source_surfaces(self.ownership, self.ownership_source_sha256,
                                 mesh_face_counts, mesh_surface_hashes)
        return self
