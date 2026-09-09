from __future__ import annotations

import math

import bpy

from bpy.types import Panel, UIList

from .core.native_loader import (
    NativeAbiMismatchError,
    NativeLibraryLoadError,
    NativeLibraryNotFoundError,
    find_native_library,
    load_native_library,
)
from .translations import tr
from .version import get_version_label


class BPT_UL_ProjectionViews(UIList):
    def draw_item(
        self,
        context: bpy.types.Context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index: int,
    ) -> None:
        projection = item

        row = layout.row(
            align=True,
        )

        row.prop(
            projection,
            "enabled",
            text="",
        )

        row.prop(
            projection,
            "name",
            text="",
            emboss=False,
            icon="CAMERA_DATA",
        )

        row.label(
            text=f"{math.degrees(projection.azimuth):.1f}°",
        )


class BPT_PT_MainPanel(Panel):
    bl_label = "Projection Tool"
    bl_idname = "BPT_PT_main_panel"

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Projection Tool"

    def draw(
        self,
        context: bpy.types.Context,
    ) -> None:
        layout = self.layout
        settings = context.scene.bpt_settings

        self._draw_header(
            layout
        )

        self._draw_native_status(
            layout
        )

        self._draw_projection_section(
            layout,
            settings,
        )

        self._draw_diagnostics(
            layout,
            settings,
        )

        self._draw_generation_section(
            layout,
            settings,
        )

        layout.separator()

        button = layout.row()
        button.scale_y = 1.6

        button.operator(
            "bpt.generate_character",
            text=tr("generate_scan"),
            icon="OUTLINER_OB_MESH",
        )

        layout.separator()

        self._draw_workflow_info(
            layout
        )

    def _draw_header(
        self,
        layout,
    ) -> None:
        row = layout.row()

        row.label(
            text="Native C++",
            icon="CONSOLE",
        )

        version_row = row.row()
        version_row.alignment = "RIGHT"

        version_row.label(
            text=get_version_label(),
            icon="INFO",
        )

    def _draw_native_status(
        self,
        layout,
    ) -> None:
        box = layout.box()

        box.label(
            text="Native Engine",
            icon="PREFERENCES",
        )

        try:
            path = find_native_library()

            library = load_native_library(
                path
            )

            abi = int(
                library.bpt_abi_version()
            )

            row = box.row()

            row.label(
                text="Status",
            )

            row.label(
                text="Ready",
                icon="CHECKMARK",
            )

            row = box.row()

            row.label(
                text="ABI",
            )

            row.label(
                text=str(abi),
            )

            row = box.row()

            row.label(
                text="Library",
            )

            row.label(
                text=path.name,
            )

        except NativeLibraryNotFoundError:
            row = box.row()

            row.alert = True

            row.label(
                text="Native library not found",
                icon="ERROR",
            )

        except NativeAbiMismatchError as exc:
            row = box.row()

            row.alert = True

            row.label(
                text="ABI mismatch",
                icon="ERROR",
            )

            details = box.row()

            details.label(
                text=str(exc),
            )

        except NativeLibraryLoadError as exc:
            row = box.row()

            row.alert = True

            row.label(
                text="Native library failed to load",
                icon="ERROR",
            )

            details = box.row()

            details.label(
                text=str(exc),
            )

        except Exception as exc:
            row = box.row()

            row.alert = True

            row.label(
                text="Native engine error",
                icon="ERROR",
            )

            details = box.row()

            details.label(
                text=str(exc),
            )

    def _draw_projection_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        header = box.row()

        header.label(
            text=tr("projection_views"),
            icon="CAMERA_DATA",
        )

        header.label(
            text=str(
                len(
                    settings.projections
                )
            ),
        )

        row = box.row()

        row.template_list(
            "BPT_UL_ProjectionViews",
            "",
            settings,
            "projections",
            settings,
            "active_projection_index",
            rows=5,
        )

        controls = row.column(
            align=True,
        )

        controls.operator(
            "bpt.add_projection",
            text="",
            icon="ADD",
        )

        if len(settings.projections) > 0:
            remove = controls.operator(
                "bpt.remove_projection",
                text="",
                icon="REMOVE",
            )

            remove.index = (
                settings.active_projection_index
            )

        box.separator()

        preset_box = box.box()

        preset_box.label(
            text=tr("turntable_presets"),
            icon="FILE_REFRESH",
        )

        quick_row = preset_box.row()

        quick_row.operator(
            "bpt.add_front_side_preset",
            text=tr("front_side_preset"),
            icon="AXIS_FRONT",
        )

        preset_row = preset_box.row(
            align=True,
        )

        preset_4 = preset_row.operator(
            "bpt.add_turntable_preset",
            text="4",
        )

        preset_4.view_count = 4

        preset_8 = preset_row.operator(
            "bpt.add_turntable_preset",
            text="8",
        )

        preset_8.view_count = 8

        preset_16 = preset_row.operator(
            "bpt.add_turntable_preset",
            text="16",
        )

        preset_16.view_count = 16

        import_row = preset_box.row()

        import_row.operator(
            "bpt.import_turntable_images",
            text=tr("import_turntable_images"),
            icon="FILE_FOLDER",
        )

        if not settings.projections:
            return

        index = min(
            settings.active_projection_index,
            len(settings.projections) - 1,
        )

        projection = (
            settings.projections[
                index
            ]
        )

        detail_box = box.box()

        detail_box.label(
            text=tr("selected_projection"),
            icon="IMAGE_DATA",
        )

        detail_box.prop(
            projection,
            "enabled",
            text=tr("enabled"),
        )

        detail_box.prop(
            projection,
            "name",
            text=tr("name"),
        )

        detail_box.prop(
            projection,
            "image",
            text=tr("image"),
        )

        load_row = detail_box.row()

        load_op = load_row.operator(
            "bpt.load_projection_image",
            text=tr("load_image"),
            icon="FILE_IMAGE",
        )

        load_op.index = index

        detail_box.prop(
            projection,
            "azimuth",
            text=tr("azimuth"),
        )

        detail_box.prop(
            projection,
            "elevation",
            text=tr("elevation"),
        )

        detail_box.prop(
            projection,
            "flip_x",
            text=tr("flip_x"),
        )

    def _draw_diagnostics(
        self,
        layout,
        settings,
    ) -> None:
        active_views = 0
        ready_views = 0
        missing_images = 0

        for projection in settings.projections:
            if not projection.enabled:
                continue

            active_views += 1

            if projection.image is None:
                missing_images += 1
            else:
                ready_views += 1

        box = layout.box()

        box.label(
            text=tr("diagnostics"),
            icon="INFO",
        )

        row = box.row()

        row.label(
            text=tr("active_views"),
        )

        row.label(
            text=str(
                active_views
            ),
        )

        row = box.row()

        row.label(
            text="Ready views",
        )

        row.label(
            text=str(
                ready_views
            ),
            icon=(
                "CHECKMARK"
                if ready_views >= 2
                else "ERROR"
            ),
        )

        row = box.row()

        row.label(
            text=tr("missing_images"),
        )

        if missing_images == 0:
            row.label(
                text="0",
                icon="CHECKMARK",
            )
        else:
            row.label(
                text=str(
                    missing_images
                ),
                icon="ERROR",
            )

        if ready_views < 2:
            warning = box.row()

            warning.alert = True

            warning.label(
                text="At least 2 ready projections required",
                icon="ERROR",
            )

    def _draw_generation_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        box.label(
            text=tr("generation"),
            icon="MESH_CUBE",
        )

        box.prop(
            settings,
            "generation_mode",
            text="Engine",
        )

        box.prop(
            settings,
            "resolution",
            text=tr("resolution"),
            slider=True,
        )

        box.prop(
            settings,
            "alpha_threshold",
            text=tr("threshold"),
            slider=True,
        )

        box.prop(
            settings,
            "symmetry_x",
            text=tr("symmetry_x"),
        )

        performance_box = box.box()

        performance_box.label(
            text="Performance",
            icon="TIME",
        )

        performance_box.prop(
            settings,
            "thread_count",
            text="Threads",
        )

        if settings.thread_count == 0:
            performance_box.label(
                text="0 = automatic CPU detection",
                icon="INFO",
            )

        quality_box = box.box()

        quality_box.label(
            text="Output",
            icon="OBJECT_DATA",
        )

        quality_box.prop(
            settings,
            "normalize_height",
            text=tr("normalize_height"),
        )

        if settings.normalize_height:
            quality_box.prop(
                settings,
                "target_height",
                text=tr("target_height"),
            )

    def _draw_workflow_info(
        self,
        layout,
    ) -> None:
        info_box = layout.box()

        info_box.label(
            text=tr("workflow"),
            icon="INFO",
        )

        info_box.label(
            text=tr("use_transparent"),
        )

        info_box.label(
            text=tr("more_angles"),
        )

        info_box.label(
            text=tr("start_low"),
        )

        info_box.separator()

        info_box.label(
            text="Native pipeline:",
            icon="CONSOLE",
        )

        info_box.label(
            text="Images → Masks → C++ Hull → Mesh",
        )


CLASSES = (
    BPT_UL_ProjectionViews,
    BPT_PT_MainPanel,
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