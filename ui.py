# ui.py

from __future__ import annotations

import bpy

from bpy.types import Panel, UIList


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
            text=f"{projection.azimuth:.1f}°",
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

        self._draw_projection_section(
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
            text="Generate Scan",
            icon="OUTLINER_OB_MESH",
        )

        layout.separator()

        info_box = layout.box()

        info_box.label(
            text="Workflow",
            icon="INFO",
        )

        info_box.label(
            text="Use transparent silhouettes.",
        )

        info_box.label(
            text="More angles = tighter visual hull.",
        )

        info_box.label(
            text="Start at 64-96 voxels.",
        )

    def _draw_projection_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        header = box.row()

        header.label(
            text="Projection Views",
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
            text="Turntable Presets",
            icon="FILE_REFRESH",
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
            text="Selected Projection",
            icon="IMAGE_DATA",
        )

        detail_box.prop(
            projection,
            "enabled",
        )

        detail_box.prop(
            projection,
            "name",
        )

        detail_box.prop(
            projection,
            "image",
        )

        angle_row = detail_box.row(
            align=True,
        )

        angle_row.prop(
            projection,
            "azimuth",
        )

        angle_row.prop(
            projection,
            "elevation",
        )

        detail_box.prop(
            projection,
            "flip_x",
        )

    def _draw_generation_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        box.label(
            text="Generation",
            icon="MESH_CUBE",
        )

        box.prop(
            settings,
            "generation_mode",
        )

        box.prop(
            settings,
            "resolution",
            slider=True,
        )

        box.prop(
            settings,
            "alpha_threshold",
            slider=True,
        )

        box.prop(
            settings,
            "symmetry_x",
        )

        scale_box = box.box()

        scale_box.label(
            text="Scale",
            icon="EMPTY_ARROWS",
        )

        scale_box.prop(
            settings,
            "normalize_height",
        )

        if settings.normalize_height:
            scale_box.prop(
                settings,
                "target_height",
            )

    def _draw_cleanup_section(
        self,
        layout,
        settings,
    ) -> None:
        box = layout.box()

        box.label(
            text="Cleanup",
            icon="MOD_REMESH",
        )

        box.prop(
            settings,
            "auto_remesh",
        )

        if settings.auto_remesh:
            box.prop(
                settings,
                "voxel_size",
            )

        box.prop(
            settings,
            "smooth_iterations",
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