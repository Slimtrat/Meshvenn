# operators.py

from __future__ import annotations

import math

import bpy

from bpy.props import IntProperty
from bpy.types import Operator

from .core.cleanup import cleanup_generated_object
from .core.masks import rgba_to_mask
from .core.mesh_builder import (
    build_surface_mesh,
    scale_mesh_to_height,
)
from .core.visual_hull import (
    ProjectionView,
    VisualHullOptions,
    build_visual_hull,
    crop_empty_bounds,
)


class BPT_OT_AddProjection(Operator):
    bl_idname = "bpt.add_projection"
    bl_label = "Add Projection"
    bl_description = "Add a new arbitrary projection view"

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = context.scene.bpt_settings

        projection = settings.projections.add()
        projection.name = f"Projection {len(settings.projections)}"
        projection.azimuth = 0.0
        projection.elevation = 0.0
        projection.enabled = True

        settings.active_projection_index = len(settings.projections) - 1

        return {"FINISHED"}


class BPT_OT_RemoveProjection(Operator):
    bl_idname = "bpt.remove_projection"
    bl_label = "Remove Projection"
    bl_description = "Remove the selected projection"

    index: IntProperty()

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = context.scene.bpt_settings

        if not settings.projections:
            return {"CANCELLED"}

        index = min(
            max(self.index, 0),
            len(settings.projections) - 1,
        )

        settings.projections.remove(index)

        if settings.projections:
            settings.active_projection_index = min(
                index,
                len(settings.projections) - 1,
            )
        else:
            settings.active_projection_index = 0

        return {"FINISHED"}


class BPT_OT_AddTurntablePreset(Operator):
    bl_idname = "bpt.add_turntable_preset"
    bl_label = "Add Turntable Preset"
    bl_description = "Add evenly spaced horizontal projection slots"

    view_count: IntProperty(
        name="Views",
        default=8,
        min=3,
        max=64,
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = context.scene.bpt_settings

        settings.projections.clear()

        angle_step = 360.0 / self.view_count

        for index in range(self.view_count):
            projection = settings.projections.add()

            angle_deg = index * angle_step

            projection.name = f"{angle_deg:.1f}°"
            projection.azimuth = math.radians(angle_deg)
            projection.elevation = 0.0
            projection.enabled = True

        settings.active_projection_index = 0

        return {"FINISHED"}


class BPT_OT_AddFrontSidePreset(Operator):
    bl_idname = "bpt.add_front_side_preset"
    bl_label = "Front + Side"
    bl_description = "Create a simple front and side projection setup"

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = context.scene.bpt_settings

        settings.projections.clear()

        front = settings.projections.add()
        front.name = "Front"
        front.azimuth = math.radians(0.0)
        front.elevation = 0.0
        front.enabled = True

        side = settings.projections.add()
        side.name = "Right"
        side.azimuth = math.radians(90.0)
        side.elevation = 0.0
        side.enabled = True

        settings.active_projection_index = 0

        return {"FINISHED"}


class BPT_OT_GenerateCharacter(Operator):
    bl_idname = "bpt.generate_character"
    bl_label = "Generate Scan"
    bl_description = (
        "Generate a 3D visual hull from all enabled projection silhouettes"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = context.scene.bpt_settings

        try:
            projections = _build_projection_views(settings)

            if len(projections) < 2:
                self.report(
                    {"ERROR"},
                    "At least two enabled projections with images are required.",
                )
                return {"CANCELLED"}

            options = VisualHullOptions(
                resolution=settings.resolution,
                symmetry_x=settings.symmetry_x,
            )

            volume = build_visual_hull(
                projections,
                options=options,
            )

            if volume.occupied_count == 0:
                self.report(
                    {"ERROR"},
                    (
                        "The projections produced an empty volume. "
                        "Check image alignment, angles and alpha masks."
                    ),
                )
                return {"CANCELLED"}

            volume = crop_empty_bounds(volume)

            mesh_data = build_surface_mesh(
                volume,
                voxel_size=1.0,
                center=True,
            )

            if settings.normalize_height:
                mesh_data = scale_mesh_to_height(
                    mesh_data,
                    settings.target_height,
                )

            obj = _create_blender_mesh(
                context,
                mesh_data.vertices,
                mesh_data.faces,
            )

            cleanup_generated_object(
                obj,
                auto_remesh=settings.auto_remesh,
                voxel_size=settings.voxel_size,
                smooth_iterations=settings.smooth_iterations,
            )

            obj["bpt_projection_count"] = len(projections)
            obj["bpt_resolution"] = settings.resolution
            obj["bpt_occupied_voxels"] = volume.occupied_count

            self.report(
                {"INFO"},
                (
                    f"Scan generated from {len(projections)} projections: "
                    f"{volume.occupied_count} occupied voxels."
                ),
            )

            return {"FINISHED"}

        except Exception as exc:
            self.report(
                {"ERROR"},
                f"Generation failed: {exc}",
            )

            return {"CANCELLED"}


def _build_projection_views(
    settings,
) -> list[ProjectionView]:
    projections: list[ProjectionView] = []

    for item in settings.projections:
        if not item.enabled:
            continue

        if item.image is None:
            continue

        mask = _image_to_mask(
            item.image,
            settings.alpha_threshold,
        )

        projections.append(
            ProjectionView(
                mask=mask,
                azimuth_degrees=math.degrees(item.azimuth),
                elevation_degrees=math.degrees(item.elevation),
                flip_x=item.flip_x,
                enabled=True,
            )
        )

    return projections


def _image_to_mask(
    image: bpy.types.Image,
    alpha_threshold: float,
):
    if image.size[0] <= 0 or image.size[1] <= 0:
        raise ValueError(
            f'Image "{image.name}" has invalid dimensions.'
        )

    image.update()

    width = image.size[0]
    height = image.size[1]

    pixels = tuple(image.pixels[:])

    return rgba_to_mask(
        pixels=pixels,
        width=width,
        height=height,
        alpha_threshold=alpha_threshold,
    )


def _create_blender_mesh(
    context: bpy.types.Context,
    vertices,
    faces,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(
        "ProjectionToolMesh",
    )

    mesh.from_pydata(
        vertices,
        [],
        faces,
    )

    mesh.update()

    obj = bpy.data.objects.new(
        "ProjectionToolScan",
        mesh,
    )

    collection = context.collection

    if collection is None:
        collection = context.scene.collection

    collection.objects.link(obj)

    bpy.ops.object.select_all(
        action="DESELECT",
    )

    obj.select_set(True)
    context.view_layer.objects.active = obj

    return obj


CLASSES = (
    BPT_OT_AddProjection,
    BPT_OT_RemoveProjection,
    BPT_OT_AddTurntablePreset,
    BPT_OT_AddFrontSidePreset,
    BPT_OT_GenerateCharacter,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)