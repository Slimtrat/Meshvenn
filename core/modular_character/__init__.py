"""Generic modular regions and sockets without Blender/runtime dependencies."""

from .coordinates import CoordinateConvention, NormalizationConvention
from .ownership import mesh_surface_sha256
from .parts import RegionSpec, SeamDeclarations, SocketSpec
from .partition import FacePartition, partition_faces
from .spec import CONTRACT_ID, CONTRACT_VERSION, ModularCharacterSpec

__all__ = ("CONTRACT_ID", "CONTRACT_VERSION", "CoordinateConvention", "NormalizationConvention",
           "RegionSpec", "SocketSpec", "SeamDeclarations", "ModularCharacterSpec",
           "FacePartition", "partition_faces", "mesh_surface_sha256")
