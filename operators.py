from __future__ import annotations

import math
import os
import re

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .core.image_mask import rgba_to_mask
from .core.native_bridge import (
    NativeCore,
    NativeProjection,
)
from .core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)


IMAGE_FILTER = (
    "*.png;"
    "*.jpg;"
    "*.jpeg;"
    "*.webp;"
    "*.bmp;"
    "*.tif;"
    "*.tiff"
)

ANGLE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3})(?:deg|°)?(?!\d)",
    re.IGNORECASE,
)


# ---------------------------------------------------------
# Image loading
# ---------------------------------------------------------


class BPT_OT_LoadProjectionImage(
    Operator,
    ImportHelper,
):
    bl_idname = "bpt.load_projection_image"
    bl_label = "Load Projection Image"
    bl_description = (
        "Load an image from disk and assign it "
        "to the selected projection"
    )

    filename_ext = ".png"

    filter_glob: StringProperty(
        default=IMAGE_FILTER,
        options={"HIDDEN"},
    )

    index: IntProperty(
        name="Projection Index",
        default=0,
        min=0,
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        if (
            self.index < 0
            or self.index
            >= len(settings.projections)
        ):
            self.report(
                {"ERROR"},
                "Invalid projection index.",
            )

            return {
                "CANCELLED"
            }

        try:
            image = bpy.data.images.load(
                self.filepath,
                check_existing=True,
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                f"Could not load image: {exc}",
            )

            return {
                "CANCELLED"
            }

        settings.projections[
            self.index
        ].image = image

        settings.active_projection_index = (
            self.index
        )

        self.report(
            {"INFO"},
            f'Loaded image "{image.name}".',
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Multi-image import
# ---------------------------------------------------------


class BPT_OT_ImportTurntableImages(
    Operator,
    ImportHelper,
):
    bl_idname = (
        "bpt.import_turntable_images"
    )

    bl_label = (
        "Import Turntable Images"
    )

    bl_description = (
        "Import multiple images and create "
        "projection views automatically"
    )

    filename_ext = ".png"

    filter_glob: StringProperty(
        default=IMAGE_FILTER,
        options={"HIDDEN"},
    )

    files: CollectionProperty(
        type=(
            bpy.types
            .OperatorFileListElement
        ),
        options={
            "HIDDEN",
            "SKIP_SAVE",
        },
    )

    clear_existing: BoolProperty(
        name="Clear Existing",
        description=(
            "Remove existing projections "
            "before importing"
        ),
        default=True,
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        selected_files = (
            self._collect_selected_files()
        )

        if not selected_files:
            self.report(
                {"ERROR"},
                "No image files selected.",
            )

            return {
                "CANCELLED"
            }

        try:
            entries = self._build_entries(
                selected_files
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                f"Image import failed: {exc}",
            )

            return {
                "CANCELLED"
            }

        if self.clear_existing:
            settings.projections.clear()

        for entry in entries:
            projection = (
                settings.projections.add()
            )

            projection.name = (
                entry["name"]
            )

            projection.azimuth = (
                math.radians(
                    entry["angle_deg"]
                )
            )

            projection.elevation = 0.0
            projection.enabled = True
            projection.flip_x = False

            projection.image = (
                entry["image"]
            )

        settings.active_projection_index = 0

        self.report(
            {"INFO"},
            (
                f"Imported "
                f"{len(entries)} "
                f"projection images."
            ),
        )

        return {
            "FINISHED"
        }

    def _collect_selected_files(
        self,
    ) -> list[str]:
        if self.files:
            return [
                os.path.join(
                    self.directory,
                    file.name,
                )
                for file
                in self.files
            ]

        if self.filepath:
            return [
                self.filepath
            ]

        return []

    def _build_entries(
        self,
        filepaths: list[str],
    ) -> list[dict]:
        loaded = []

        for filepath in sorted(
            filepaths
        ):
            image = bpy.data.images.load(
                filepath,
                check_existing=True,
            )

            stem = os.path.splitext(
                os.path.basename(
                    filepath
                )
            )[0]

            angle = (
                _extract_angle_from_name(
                    stem
                )
            )

            loaded.append(
                {
                    "filepath": filepath,
                    "stem": stem,
                    "image": image,
                    "angle_deg": angle,
                }
            )

        if any(
            item["angle_deg"] is None
            for item in loaded
        ):
            step = (
                360.0
                / max(
                    len(loaded),
                    1,
                )
            )

            for index, item in enumerate(
                loaded
            ):
                if (
                    item["angle_deg"]
                    is None
                ):
                    item[
                        "angle_deg"
                    ] = (
                        index
                        * step
                    )

        loaded.sort(
            key=lambda item: (
                item["angle_deg"]
            )
        )

        entries = []

        for item in loaded:
            angle = (
                float(
                    item["angle_deg"]
                )
                % 360.0
            )

            entries.append(
                {
                    "name": (
                        f"{angle:.1f}° "
                        f"- {item['stem']}"
                    ),
                    "angle_deg": angle,
                    "image": item["image"],
                }
            )

        return entries

    def invoke(
        self,
        context: bpy.types.Context,
        event,
    ) -> set[str]:
        context.window_manager.fileselect_add(
            self
        )

        return {
            "RUNNING_MODAL"
        }


# ---------------------------------------------------------
# Projection management
# ---------------------------------------------------------


class BPT_OT_AddProjection(
    Operator
):
    bl_idname = "bpt.add_projection"
    bl_label = "Add Projection"

    bl_description = (
        "Add a new arbitrary projection view"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        projection = (
            settings.projections.add()
        )

        projection.name = (
            f"Projection "
            f"{len(settings.projections)}"
        )

        projection.azimuth = 0.0
        projection.elevation = 0.0
        projection.enabled = True

        settings.active_projection_index = (
            len(
                settings.projections
            )
            - 1
        )

        return {
            "FINISHED"
        }


class BPT_OT_RemoveProjection(
    Operator
):
    bl_idname = "bpt.remove_projection"
    bl_label = "Remove Projection"

    bl_description = (
        "Remove the selected projection"
    )

    index: IntProperty()

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        if not settings.projections:
            return {
                "CANCELLED"
            }

        index = min(
            max(
                self.index,
                0,
            ),
            len(
                settings.projections
            )
            - 1,
        )

        settings.projections.remove(
            index
        )

        if settings.projections:
            settings.active_projection_index = (
                min(
                    index,
                    len(
                        settings.projections
                    )
                    - 1,
                )
            )
        else:
            settings.active_projection_index = 0

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Presets
# ---------------------------------------------------------


class BPT_OT_AddTurntablePreset(
    Operator
):
    bl_idname = (
        "bpt.add_turntable_preset"
    )

    bl_label = (
        "Add Turntable Preset"
    )

    bl_description = (
        "Add evenly spaced horizontal "
        "projection slots"
    )

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
        settings = (
            context.scene.bpt_settings
        )

        settings.projections.clear()

        angle_step = (
            360.0
            / self.view_count
        )

        for index in range(
            self.view_count
        ):
            projection = (
                settings
                .projections
                .add()
            )

            angle_deg = (
                index
                * angle_step
            )

            projection.name = (
                f"{angle_deg:.1f}°"
            )

            projection.azimuth = (
                math.radians(
                    angle_deg
                )
            )

            projection.elevation = 0.0
            projection.enabled = True
            projection.flip_x = False

        settings.active_projection_index = 0

        return {
            "FINISHED"
        }


class BPT_OT_AddFrontSidePreset(
    Operator
):
    bl_idname = (
        "bpt.add_front_side_preset"
    )

    bl_label = (
        "Front + Side"
    )

    bl_description = (
        "Create a simple front and side "
        "projection setup"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        settings.projections.clear()

        front = (
            settings.projections.add()
        )

        front.name = "Front"

        front.azimuth = (
            math.radians(
                0.0
            )
        )

        front.elevation = 0.0
        front.enabled = True
        front.flip_x = False

        side = (
            settings.projections.add()
        )

        side.name = "Right"

        side.azimuth = (
            math.radians(
                90.0
            )
        )

        side.elevation = 0.0
        side.enabled = True
        side.flip_x = False

        settings.active_projection_index = 0

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Native C++ scan
# ---------------------------------------------------------


class BPT_OT_GenerateCharacter(
    Operator
):
    bl_idname = (
        "bpt.generate_character"
    )

    bl_label = (
        "Generate Scan"
    )

    bl_description = (
        "Generate a native C++ visual hull "
        "from all enabled projection silhouettes"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context.scene.bpt_settings
        )

        try:
            projections = (
                _build_native_projections(
                    settings
                )
            )

            if len(projections) < 2:
                self.report(
                    {"ERROR"},
                    (
                        "At least two enabled "
                        "projections with images "
                        "are required."
                    ),
                )

                return {
                    "CANCELLED"
                }

            core = NativeCore()

            volume = (
                core.build_visual_hull(
                    projections,
                    resolution=(
                        settings.resolution
                    ),
                    symmetry_x=(
                        settings.symmetry_x
                    ),
                    thread_count=(
                        settings.thread_count
                    ),
                )
            )

            if (
                volume.occupied_count
                == 0
            ):
                self.report(
                    {"ERROR"},
                    (
                        "The projections produced "
                        "an empty native volume. "
                        "Check image alignment, "
                        "angles and alpha masks."
                    ),
                )

                return {
                    "CANCELLED"
                }

            native_mesh = (
                core.build_surface_mesh(
                    volume,
                    voxel_size=1.0,
                    center_xy=True,
                )
            )

            if (
                native_mesh.vertex_count
                == 0
            ):
                self.report(
                    {"ERROR"},
                    (
                        "Native mesh generation "
                        "returned no vertices."
                    ),
                )

                return {
                    "CANCELLED"
                }

            obj = (
                create_blender_mesh_from_native(
                    native_mesh,
                    mesh_name=(
                        "ProjectionToolNativeMesh"
                    ),
                    object_name=(
                        "ProjectionToolScan"
                    ),
                )
            )

            if (
                settings.normalize_height
            ):
                _scale_object_to_height(
                    obj,
                    settings.target_height,
                )

            shade_smooth_native_object(
                obj
            )

            obj[
                "bpt_engine"
            ] = "native-cpp"

            obj[
                "bpt_projection_count"
            ] = len(
                projections
            )

            obj[
                "bpt_resolution"
            ] = (
                settings.resolution
            )

            obj[
                "bpt_threads"
            ] = (
                settings.thread_count
            )

            obj[
                "bpt_occupied_voxels"
            ] = (
                volume.occupied_count
            )

            obj[
                "bpt_native_vertices"
            ] = (
                native_mesh.vertex_count
            )

            obj[
                "bpt_native_polygons"
            ] = (
                native_mesh.polygon_count
            )

            self.report(
                {"INFO"},
                (
                    "Native scan generated from "
                    f"{len(projections)} projections: "
                    f"{volume.occupied_count} voxels, "
                    f"{native_mesh.vertex_count} vertices."
                ),
            )

            return {
                "FINISHED"
            }

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Native generation failed: "
                    f"{exc}"
                ),
            )

            return {
                "CANCELLED"
            }


# ---------------------------------------------------------
# Native conversion helpers
# ---------------------------------------------------------


def _build_native_projections(
    settings,
) -> list[
    NativeProjection
]:
    projections: list[
        NativeProjection
    ] = []

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
            NativeProjection(
                mask=mask,
                azimuth_degrees=(
                    math.degrees(
                        item.azimuth
                    )
                ),
                elevation_degrees=(
                    math.degrees(
                        item.elevation
                    )
                ),
                flip_x=(
                    item.flip_x
                ),
            )
        )

    return projections


def _image_to_mask(
    image: bpy.types.Image,
    alpha_threshold: float,
):
    if (
        image.size[0] <= 0
        or image.size[1] <= 0
    ):
        raise ValueError(
            (
                f'Image "{image.name}" '
                "has invalid dimensions."
            )
        )

    image.update()

    width = int(
        image.size[0]
    )

    height = int(
        image.size[1]
    )

    pixels = tuple(
        image.pixels[:]
    )

    return rgba_to_mask(
        pixels=pixels,
        width=width,
        height=height,
        alpha_threshold=(
            alpha_threshold
        ),
    )


def _scale_object_to_height(
    obj: bpy.types.Object,
    target_height: float,
) -> None:
    if target_height <= 0.0:
        raise ValueError(
            (
                "Target height must be "
                "greater than zero."
            )
        )

    current_height = float(
        obj.dimensions.z
    )

    if current_height <= 0.0:
        return

    scale = (
        target_height
        / current_height
    )

    obj.scale = (
        scale,
        scale,
        scale,
    )

    bpy.context.view_layer.objects.active = (
        obj
    )

    obj.select_set(
        True
    )

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True,
    )


# ---------------------------------------------------------
# Filename angle detection
# ---------------------------------------------------------


def _extract_angle_from_name(
    name: str,
) -> float | None:
    match = ANGLE_PATTERN.search(
        name
    )

    if not match:
        lowered = (
            name.lower()
        )

        if "front" in lowered:
            return 0.0

        if (
            "right" in lowered
            or "side" in lowered
        ):
            return 90.0

        if "back" in lowered:
            return 180.0

        if "left" in lowered:
            return 270.0

        return None

    return float(
        int(
            match.group(1)
        )
        % 360
    )


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------


CLASSES = (
    BPT_OT_LoadProjectionImage,
    BPT_OT_ImportTurntableImages,
    BPT_OT_AddProjection,
    BPT_OT_RemoveProjection,
    BPT_OT_AddTurntablePreset,
    BPT_OT_AddFrontSidePreset,
    BPT_OT_GenerateCharacter,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )


def unregister() -> None:
    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )