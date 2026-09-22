"""Blender-independent UV texture baking API."""

from .api import bake_uv_texture, square_texture_config, texture_memory_bytes
from .constants import (
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_PADDING_PIXELS,
    DEFAULT_SAMPLES_PER_AXIS,
    DEFAULT_TEXTURE_SIZE,
    MAX_PADDING_PIXELS,
    MAX_SAMPLES_PER_AXIS,
    MAX_TEXTURE_DIMENSION,
    RGBA,
    Vector2,
    Vector3,
)
from .models import SurfaceColorSample, SurfaceColorSampler, UVBakeConfig, UVBakeTriangle, UVBakeVertex
from .texture import (
    TextureBuffer,
    UVBakeProgress,
    UVBakeProgressCallback,
    UVBakeResult,
    UVBakeStats,
)

__all__ = (
    "DEFAULT_BACKGROUND_COLOR", "DEFAULT_PADDING_PIXELS", "DEFAULT_SAMPLES_PER_AXIS",
    "DEFAULT_TEXTURE_SIZE", "MAX_PADDING_PIXELS", "MAX_SAMPLES_PER_AXIS",
    "MAX_TEXTURE_DIMENSION", "RGBA", "SurfaceColorSample", "SurfaceColorSampler",
    "TextureBuffer", "UVBakeConfig", "UVBakeProgress", "UVBakeProgressCallback",
    "UVBakeResult", "UVBakeStats", "UVBakeTriangle", "UVBakeVertex", "Vector2",
    "Vector3", "bake_uv_texture", "square_texture_config", "texture_memory_bytes",
)
