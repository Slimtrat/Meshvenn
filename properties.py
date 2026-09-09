# properties.py

from __future__ import annotations

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class BPT_PG_ProjectionView(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Projection label",
        default="Projection",
    )

    enabled: BoolProperty(
        name="Enabled",
        description="Use this projection during generation",
        default=True,
    )

    image: PointerProperty(
        name="Image",
        description="Silhouette image for this projection",
        type=bpy.types.Image,
    )

    azimuth: FloatProperty(
        name="Azimuth",
        description="Rotation around the vertical axis in degrees",
        default=0.0,
        min=-360.0,
        max=360.0,
        subtype="ANGLE",
        unit="ROTATION",
    )

    elevation: FloatProperty(
        name="Elevation",
        description="Vertical camera angle in degrees",
        default=0.0,
        min=-90.0,
        max=90.0,
        subtype="ANGLE",
        unit="ROTATION",
    )

    flip_x: BoolProperty(
        name="Flip X",
        description="Flip the silhouette horizontally before projection",
        default=False,
    )

    weight: FloatProperty(
        name="Weight",
        description="Reserved for future soft-constraint support",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )


class BPT_PG_Settings(PropertyGroup):
    projections: CollectionProperty(
        name="Projections",
        description="Projection views used for reconstruction",
        type=BPT_PG_ProjectionView,
    )

    active_projection_index: IntProperty(
        name="Active Projection Index",
        default=0,
        min=0,
    )

    resolution: IntProperty(
        name="Resolution",
        description="Voxel resolution of the generated volume",
        default=96,
        min=16,
        max=256,
    )

    alpha_threshold: FloatProperty(
        name="Threshold",
        description="Alpha threshold used to determine silhouette occupancy",
        default=0.1,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    symmetry_x: BoolProperty(
        name="Symmetry X",
        description="Force symmetry along the X axis after reconstruction",
        default=False,
    )

    smooth_iterations: IntProperty(
        name="Smooth",
        description="Number of smoothing iterations applied after mesh generation",
        default=3,
        min=0,
        max=20,
    )

    voxel_size: FloatProperty(
        name="Voxel Size",
        description="Voxel size used by Blender's voxel remesher",
        default=0.05,
        min=0.001,
        max=1.0,
        precision=3,
    )

    auto_remesh: BoolProperty(
        name="Auto Remesh",
        description="Automatically run Blender voxel remesh after generation",
        default=True,
    )

    normalize_height: BoolProperty(
        name="Normalize Height",
        description="Normalize the generated character to a predictable height",
        default=True,
    )

    target_height: FloatProperty(
        name="Target Height",
        description="Target generated character height in Blender units",
        default=2.0,
        min=0.1,
        max=100.0,
    )

    generation_mode: EnumProperty(
        name="Mode",
        description="Silhouette reconstruction strategy",
        items=(
            (
                "VISUAL_HULL",
                "Visual Hull",
                "Intersect arbitrary orthographic silhouette projections",
            ),
        ),
        default="VISUAL_HULL",
    )


def ensure_default_projections(
    settings: BPT_PG_Settings,
) -> None:
    if len(settings.projections) > 0:
        return

    defaults = (
        ("Front", 0.0, 0.0, False),
        ("Right", 90.0, 0.0, False),
        ("Back", 180.0, 0.0, False),
        ("Top", 0.0, 90.0, False),
    )

    for name, azimuth_deg, elevation_deg, flip_x in defaults:
        item = settings.projections.add()
        item.name = name
        item.azimuth = azimuth_deg
        item.elevation = elevation_deg
        item.flip_x = flip_x
        item.enabled = name in {"Front", "Right"}


def _ensure_scene_defaults(
    _scene: bpy.types.Scene,
) -> None:
    scene = bpy.context.scene

    if scene is None:
        return

    settings = getattr(scene, "bpt_settings", None)

    if settings is None:
        return

    ensure_default_projections(settings)


CLASSES = (
    BPT_PG_ProjectionView,
    BPT_PG_Settings,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.bpt_settings = PointerProperty(
        type=BPT_PG_Settings,
    )

    bpy.app.timers.register(
        _ensure_scene_defaults,
        first_interval=0.1,
    )


def unregister() -> None:
    if hasattr(bpy.types.Scene, "bpt_settings"):
        del bpy.types.Scene.bpt_settings

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)