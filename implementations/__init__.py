"""Built-in pipeline catalog and stable Blender lifecycle facade."""

from .catalog import (
    BUILTIN_DEFAULT_IMPLEMENTATION_IDS,
    BUILTIN_IMPLEMENTATION_FACTORIES,
    ImplementationFactory,
    builtin_default_id,
)
from .canonical_rig import CanonicalRigImplementation
from .native_visual_hull import NativeVisualHullImplementation
from .projected_color import ProjectedColorImplementation
from .projection_images import ProjectionImagesImplementation
from .registration import (
    builtin_implementation_count,
    register,
    register_builtin_implementations,
    registered_builtin_ids,
    unregister,
    unregister_builtin_implementations,
)
from .sdf_reconstruction import SDFReconstructionImplementation
from .uv_bake import UVBakeImplementation

__all__ = (
    "ImplementationFactory",
    "BUILTIN_IMPLEMENTATION_FACTORIES",
    "BUILTIN_DEFAULT_IMPLEMENTATION_IDS",
    "ProjectionImagesImplementation",
    "NativeVisualHullImplementation",
    "SDFReconstructionImplementation",
    "ProjectedColorImplementation",
    "UVBakeImplementation",
    "CanonicalRigImplementation",
    "register_builtin_implementations",
    "unregister_builtin_implementations",
    "register",
    "unregister",
    "registered_builtin_ids",
    "builtin_implementation_count",
    "builtin_default_id",
)
