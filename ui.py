# ui.py

from __future__ import annotations

import math

import bpy

from bpy.types import Panel, UIList

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

        version_row = layout.row()
        version_row.alignment = "RIGHT"

        version_row.label(
            text=get_version_label(),
            icon="INFO",
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

        self._draw_cleanup_section(
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
            text=str(len(settings.projections)),
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

            remove.index = settings.active_projection_index

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

        if not settings.projections:
            return

        index = min(
            settings.active_projection_index,
            len(settings.projections) - 1,
        )

        projection = settings.projections[index]

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
        missing_images = 0

        for projection in settings.projections:
            if not projection.enabled:
                continue

            active_views += 1

            if projection.image is None:
                missing_images += 1

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
            text=str(active_views),
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
                text=str(missing_images),
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
            text=tr("mode"),
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

        scale_box = box.box()

        scale_box.label(
            text=tr("scale"),
            icon="EMPTY_ARROWS",
        )

        scale_box.prop(
            settings,
            "normalize_height",
            text=tr("normalize_height"),
        )

        if settings.normalize_height:
            scale_box.prop(
                settings,
                "target_height",
                text=tr("target_height"),
            )

    def _draw_cleanup_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        box.label(
            text=tr("cleanup"),
            icon="MOD_REMESH",
        )

        box.prop(
            settings,
            "auto_remesh",
            text=tr("auto_remesh"),
        )

        if settings.auto_remesh:
            box.prop(
                settings,
                "voxel_size",
                text=tr("voxel_size"),
            )

        box.prop(
            settings,
            "smooth_iterations",
            text=tr("smooth"),
        )


CLASSES = (
    BPT_UL_ProjectionViews,
    BPT_PT_MainPanel,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)