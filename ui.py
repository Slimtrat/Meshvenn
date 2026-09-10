from __future__ import annotations

import math
import textwrap

import bpy

from bpy.types import (
    Panel,
    UIList,
)

from .core.pipeline_contracts import (
    PipelineStage,
    PIPELINE_STAGE_ORDER,
    stage_spec,
)
from .core.pipeline_registry import (
    PIPELINE_REGISTRY,
)
from .operators import (
    get_last_pipeline_context,
    get_last_pipeline_report,
)
from .properties import (
    pipeline_stage_settings,
)
from .version import (
    get_version_label,
)


# ---------------------------------------------------------
# UI constants
# ---------------------------------------------------------

STAGE_ICONS: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.INPUT:
        "CAMERA_DATA",

    PipelineStage.GEOMETRY:
        "MESH_DATA",

    PipelineStage.MATERIAL:
        "MATERIAL",

    PipelineStage.RIG:
        "ARMATURE_DATA",

    PipelineStage.EXPORT:
        "EXPORT",
}


STAGE_RUN_LABELS: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.GEOMETRY:
        "Run Geometry",

    PipelineStage.MATERIAL:
        "Build Material",

    PipelineStage.RIG:
        "Generate Rig",

    PipelineStage.EXPORT:
        "Export",
}


# ---------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------

def _draw_wrapped_text(
    layout,
    text: str,
    *,
    width: int = 42,
    icon: str = "NONE",
) -> None:
    """
    Blender labels do not wrap automatically.
    """

    normalized = (
        str(
            text
        )
        .strip()
    )

    if not normalized:
        return

    lines = textwrap.wrap(
        normalized,
        width=width,
    )

    for index, line in enumerate(
        lines
    ):
        layout.label(
            text=line,
            icon=(
                icon
                if index == 0
                else "NONE"
            ),
        )


def _descriptor_for_selection(
    stage: PipelineStage,
    implementation_id: str,
):
    if not implementation_id:
        return None

    try:
        entry = (
            PIPELINE_REGISTRY
            .require_entry(
                implementation_id
            )
        )

    except Exception:
        return None

    if (
        entry.descriptor.stage
        != stage
    ):
        return None

    return (
        entry.descriptor
    )


def _stage_status(
    context: bpy.types.Context,
    stage: PipelineStage,
):
    """
    Return:

        text
        icon
        alert
    """

    settings = (
        context
        .scene
        .bpt_settings
    )

    stage_settings = (
        pipeline_stage_settings(
            settings,
            stage,
        )
    )

    descriptors = (
        PIPELINE_REGISTRY
        .descriptors(
            stage
        )
    )

    if not descriptors:
        return (
            "Not implemented",
            "INFO",
            False,
        )

    if not stage_settings.enabled:
        return (
            "Disabled",
            "INFO",
            False,
        )

    implementation_id = (
        stage_settings
        .implementation_id
        .strip()
    )

    if not implementation_id:
        return (
            "Not configured",
            "ERROR",
            True,
        )

    descriptor = (
        _descriptor_for_selection(
            stage,
            implementation_id,
        )
    )

    if descriptor is None:
        return (
            "Implementation missing",
            "ERROR",
            True,
        )

    report = (
        get_last_pipeline_report(
            context.scene
        )
    )

    if report is not None:
        record = (
            report.record_for(
                stage
            )
        )

        if record is not None:
            if record.success:
                return (
                    "Last run OK",
                    "CHECKMARK",
                    False,
                )

            if record.failed:
                return (
                    "Last run failed",
                    "ERROR",
                    True,
                )

            if record.skipped:
                return (
                    "Skipped",
                    "INFO",
                    False,
                )

    pipeline_context = (
        get_last_pipeline_context(
            context.scene
        )
    )

    if (
        pipeline_context is not None
        and pipeline_context.has_output(
            stage
        )
    ):
        return (
            "Output ready",
            "CHECKMARK",
            False,
        )

    return (
        "Configured",
        "INFO",
        False,
    )


# ---------------------------------------------------------
# Projection UI list
# ---------------------------------------------------------

class BPT_UL_ProjectionViews(
    UIList
):
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
            align=True
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

        angle_row = row.row()

        angle_row.alignment = (
            "RIGHT"
        )

        angle_row.label(
            text=(
                f"{math.degrees(projection.azimuth):.0f}°"
            )
        )

        angle_row.label(
            text="",
            icon=(
                "CHECKMARK"
                if projection.image
                is not None
                else "ERROR"
            ),
        )


# ---------------------------------------------------------
# Main panel
# ---------------------------------------------------------

class BPT_PT_MainPanel(
    Panel
):
    bl_label = (
        "Meshvenn"
    )

    bl_idname = (
        "BPT_PT_main_panel"
    )

    bl_space_type = (
        "VIEW_3D"
    )

    bl_region_type = (
        "UI"
    )

    bl_category = (
        "Meshvenn"
    )

    # -----------------------------------------------------
    # Draw
    # -----------------------------------------------------

    def draw(
        self,
        context: bpy.types.Context,
    ) -> None:
        layout = (
            self.layout
        )

        scene = (
            context.scene
        )

        settings = getattr(
            scene,
            "bpt_settings",
            None,
        )

        if settings is None:
            box = layout.box()

            box.alert = True

            box.label(
                text=(
                    "Meshvenn settings unavailable"
                ),
                icon="ERROR",
            )

            return

        self._draw_header(
            layout
        )

        layout.separator()

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            self._draw_stage(
                layout,
                context,
                settings,
                stage,
            )

        layout.separator()

        self._draw_generate_all(
            layout,
            settings,
        )

        layout.separator()

        self._draw_last_run(
            layout,
            context,
            settings,
        )

        self._draw_advanced(
            layout,
            context,
            settings,
        )

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    def _draw_header(
        self,
        layout,
    ) -> None:
        row = layout.row(
            align=True
        )

        row.label(
            text="Meshvenn",
            icon="MESH_ICOSPHERE",
        )

        version = row.row()

        version.alignment = (
            "RIGHT"
        )

        version.label(
            text=get_version_label(),
        )

        description = (
            layout.row()
        )

        description.label(
            text=(
                "Images → Geometry → Material → Rig → Export"
            )
        )

    # -----------------------------------------------------
    # Generic stage card
    # -----------------------------------------------------

    def _draw_stage(
        self,
        layout,
        context: bpy.types.Context,
        settings,
        stage: PipelineStage,
    ) -> None:
        spec = (
            stage_spec(
                stage
            )
        )

        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        descriptors = (
            PIPELINE_REGISTRY
            .descriptors(
                stage
            )
        )

        (
            status_text,
            status_icon,
            status_alert,
        ) = _stage_status(
            context,
            stage,
        )

        box = layout.box()

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        header = box.row(
            align=True
        )

        header.prop(
            stage_settings,
            "expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if stage_settings.expanded
                else "TRIA_RIGHT"
            ),
        )

        enabled_column = (
            header.row(
                align=True
            )
        )

        enabled_column.enabled = bool(
            descriptors
        )

        enabled_column.prop(
            stage_settings,
            "enabled",
            text="",
        )

        header.label(
            text=(
                spec.label.upper()
            ),
            icon=(
                STAGE_ICONS[
                    stage
                ]
            ),
        )

        status = (
            header.row()
        )

        status.alignment = (
            "RIGHT"
        )

        status.alert = (
            status_alert
        )

        status.label(
            text=status_text,
            icon=status_icon,
        )

        if not stage_settings.expanded:
            return

        # -------------------------------------------------
        # Stage body
        # -------------------------------------------------

        body = box.column()

        self._draw_implementation_selector(
            body,
            context,
            settings,
            stage,
            descriptors,
        )

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if (
            implementation_id
            and descriptors
        ):
            body.separator()

            config = body.column()

            config.enabled = (
                stage_settings.enabled
            )

            self._draw_implementation_settings(
                config,
                context,
                settings,
                stage,
                implementation_id,
            )

        # -------------------------------------------------
        # Per-stage action
        # -------------------------------------------------

        if (
            stage
            != PipelineStage.INPUT
        ):
            self._draw_stage_action(
                body,
                stage,
                stage_settings,
                descriptors,
            )

    # -----------------------------------------------------
    # Implementation selector
    # -----------------------------------------------------

    def _draw_implementation_selector(
        self,
        layout,
        context,
        settings,
        stage: PipelineStage,
        descriptors,
    ) -> None:
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        current_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if not descriptors:
            info = layout.box()

            info.label(
                text=(
                    "No implementation registered yet"
                ),
                icon="INFO",
            )

            _draw_wrapped_text(
                info,
                (
                    "The pipeline stage already exists. "
                    "Adding an implementation will make it "
                    "available here automatically."
                ),
                width=40,
            )

            return

        selected_descriptor = (
            _descriptor_for_selection(
                stage,
                current_id,
            )
        )

        selection_box = (
            layout.box()
        )

        header = (
            selection_box.row()
        )

        header.label(
            text="Implementation",
            icon="SETTINGS",
        )

        if selected_descriptor is not None:
            selected = (
                selection_box.row(
                    align=True
                )
            )

            selected.label(
                text=(
                    selected_descriptor.label
                ),
                icon="CHECKMARK",
            )

            version = (
                selected.row()
            )

            version.alignment = (
                "RIGHT"
            )

            version.label(
                text=(
                    f"v{selected_descriptor.version}"
                )
            )

            if (
                selected_descriptor
                .description
            ):
                _draw_wrapped_text(
                    selection_box,
                    selected_descriptor
                    .description,
                    width=40,
                )

        else:
            warning = (
                selection_box.row()
            )

            warning.alert = True

            warning.label(
                text=(
                    "Select an implementation"
                ),
                icon="ERROR",
            )

        # -------------------------------------------------
        # Only show implementation choices when there is
        # something to choose.
        # -------------------------------------------------

        if (
            len(descriptors) > 1
            or selected_descriptor
            is None
        ):
            selection_box.separator()

            for descriptor in (
                descriptors
            ):
                is_selected = (
                    descriptor.identifier
                    == current_id
                )

                row = (
                    selection_box.row()
                )

                operator = row.operator(
                    (
                        "bpt."
                        "set_pipeline_implementation"
                    ),
                    text=(
                        descriptor.label
                    ),
                    icon=(
                        "CHECKMARK"
                        if is_selected
                        else "NONE"
                    ),
                    depress=(
                        is_selected
                    ),
                )

                operator.stage = (
                    stage.value
                )

                operator.implementation_id = (
                    descriptor.identifier
                )

                operator.enable_stage = True

    # -----------------------------------------------------
    # Implementation settings dispatch
    # -----------------------------------------------------

    def _draw_implementation_settings(
        self,
        layout,
        context: bpy.types.Context,
        settings,
        stage: PipelineStage,
        implementation_id: str,
    ) -> None:
        """
        Generic UI extension mechanism.

        Future implementations can optionally implement:

            draw_settings(layout, context)

        without modifying this central panel.

        Built-in implementations which predate this optional
        hook have small compatibility drawers below.
        """

        implementation = (
            PIPELINE_REGISTRY
            .get(
                implementation_id
            )
        )

        if implementation is not None:
            custom_draw = getattr(
                implementation,
                "draw_settings",
                None,
            )

            if callable(
                custom_draw
            ):
                try:
                    custom_draw(
                        layout,
                        context,
                    )

                except Exception as exc:
                    warning = (
                        layout.box()
                    )

                    warning.alert = True

                    warning.label(
                        text=(
                            "Implementation UI failed"
                        ),
                        icon="ERROR",
                    )

                    _draw_wrapped_text(
                        warning,
                        str(
                            exc
                        ),
                    )

                return

        # -------------------------------------------------
        # Current built-in compatibility drawers.
        # -------------------------------------------------

        if (
            implementation_id
            == "projection-images"
        ):
            self._draw_projection_input(
                layout,
                settings,
            )

            return

        if (
            implementation_id
            == "native-visual-hull"
        ):
            self._draw_native_geometry(
                layout,
                settings,
            )

            return

        if (
            implementation_id
            == "projected-color-v1.2"
        ):
            self._draw_projected_material(
                layout,
                implementation,
            )

            return

        # -------------------------------------------------
        # Generic fallback.
        # -------------------------------------------------

        if implementation is not None:
            descriptor = (
                implementation
                .descriptor
            )

            if descriptor.capabilities:
                capability_box = (
                    layout.box()
                )

                capability_box.label(
                    text="Capabilities",
                    icon="INFO",
                )

                for capability in (
                    descriptor.capabilities
                ):
                    capability_box.label(
                        text=(
                            capability
                        )
                    )

        else:
            warning = (
                layout.box()
            )

            warning.alert = True

            warning.label(
                text=(
                    "Implementation unavailable"
                ),
                icon="ERROR",
            )

    # -----------------------------------------------------
    # INPUT
    # -----------------------------------------------------

    def _draw_projection_input(
        self,
        layout,
        settings,
    ) -> None:
        active_views = 0

        ready_views = 0

        missing_views = 0

        for projection in (
            settings.projections
        ):
            if not projection.enabled:
                continue

            active_views += 1

            if projection.image is None:
                missing_views += 1

            else:
                ready_views += 1

        # -------------------------------------------------
        # Input status
        # -------------------------------------------------

        status = (
            layout.row(
                align=True
            )
        )

        status.label(
            text=(
                f"{ready_views}/{active_views} "
                "enabled views ready"
            ),
            icon=(
                "CHECKMARK"
                if ready_views >= 2
                else "ERROR"
            ),
        )

        # -------------------------------------------------
        # Projection list
        # -------------------------------------------------

        row = layout.row()

        row.template_list(
            "BPT_UL_ProjectionViews",
            "",
            settings,
            "projections",
            settings,
            "active_projection_index",
            rows=5,
        )

        controls = (
            row.column(
                align=True
            )
        )

        controls.operator(
            "bpt.add_projection",
            text="",
            icon="ADD",
        )

        if len(
            settings.projections
        ) > 0:
            remove = (
                controls.operator(
                    "bpt.remove_projection",
                    text="",
                    icon="REMOVE",
                )
            )

            remove.index = (
                settings
                .active_projection_index
            )

        # -------------------------------------------------
        # Import / presets
        # -------------------------------------------------

        tools = (
            layout.box()
        )

        tools.label(
            text="Add Views",
            icon="CAMERA_DATA",
        )

        import_row = (
            tools.row()
        )

        import_row.operator(
            (
                "bpt."
                "import_turntable_images"
            ),
            text="Import Images",
            icon="FILE_FOLDER",
        )

        preset = (
            tools.row(
                align=True
            )
        )

        preset.operator(
            (
                "bpt."
                "add_front_side_preset"
            ),
            text="Front + Side",
        )

        for count in (
            4,
            8,
            16,
        ):
            operator = (
                preset.operator(
                    (
                        "bpt."
                        "add_turntable_preset"
                    ),
                    text=str(
                        count
                    ),
                )
            )

            operator.view_count = (
                count
            )

        # -------------------------------------------------
        # Selected projection
        # -------------------------------------------------

        if settings.projections:
            index = min(
                settings
                .active_projection_index,
                len(
                    settings.projections
                )
                - 1,
            )

            projection = (
                settings.projections[
                    index
                ]
            )

            detail = (
                layout.box()
            )

            detail.label(
                text="Selected View",
                icon="IMAGE_DATA",
            )

            detail.prop(
                projection,
                "enabled",
            )

            detail.prop(
                projection,
                "name",
            )

            detail.prop(
                projection,
                "image",
            )

            load = (
                detail.operator(
                    (
                        "bpt."
                        "load_projection_image"
                    ),
                    text="Load Image",
                    icon="FILE_IMAGE",
                )
            )

            load.index = (
                index
            )

            detail.prop(
                projection,
                "azimuth",
            )

            detail.prop(
                projection,
                "elevation",
            )

            detail.prop(
                projection,
                "flip_x",
            )

            detail.prop(
                projection,
                "weight",
                slider=True,
            )

        # -------------------------------------------------
        # Input extraction
        # -------------------------------------------------

        extraction = (
            layout.box()
        )

        extraction.label(
            text="Silhouette",
            icon="MOD_MASK",
        )

        extraction.prop(
            settings,
            "alpha_threshold",
            text="Alpha Threshold",
            slider=True,
        )

        if ready_views < 2:
            warning = (
                extraction.row()
            )

            warning.alert = True

            warning.label(
                text=(
                    "At least 2 images required"
                ),
                icon="ERROR",
            )

        elif missing_views > 0:
            warning = (
                extraction.row()
            )

            warning.label(
                text=(
                    f"{missing_views} enabled view"
                    + (
                        "s"
                        if missing_views != 1
                        else ""
                    )
                    + " without image"
                ),
                icon="INFO",
            )

    # -----------------------------------------------------
    # GEOMETRY
    # -----------------------------------------------------

    def _draw_native_geometry(
        self,
        layout,
        settings,
    ) -> None:
        quality = (
            layout.box()
        )

        quality.label(
            text="Reconstruction",
            icon="MESH_DATA",
        )

        quality.prop(
            settings,
            "resolution",
            text="Resolution",
            slider=True,
        )

        quality.prop(
            settings,
            "symmetry_x",
            text="Symmetry X",
        )

        quality.label(
            text=(
                "Surface: Surface Nets"
            ),
            icon="INFO",
        )

        performance = (
            layout.box()
        )

        performance.label(
            text="Performance",
            icon="TIME",
        )

        performance.prop(
            settings,
            "thread_count",
            text="Threads",
        )

        if (
            settings.thread_count
            == 0
        ):
            performance.label(
                text=(
                    "0 = automatic CPU detection"
                ),
                icon="INFO",
            )

        output = (
            layout.box()
        )

        output.label(
            text="Output",
            icon="OBJECT_DATA",
        )

        output.prop(
            settings,
            "normalize_height",
            text="Normalize Height",
        )

        if settings.normalize_height:
            output.prop(
                settings,
                "target_height",
                text="Target Height",
            )

    # -----------------------------------------------------
    # MATERIAL
    # -----------------------------------------------------

    def _draw_projected_material(
        self,
        layout,
        implementation,
    ) -> None:
        info = (
            layout.box()
        )

        info.label(
            text="Projected Color V1.2",
            icon="MATERIAL",
        )

        info.label(
            text="Visibility-aware projection",
            icon="CHECKMARK",
        )

        info.label(
            text="Adaptive multi-view blend",
            icon="CHECKMARK",
        )

        info.label(
            text="Top-K contributors",
            icon="CHECKMARK",
        )

        info.label(
            text="Backface safety fallback",
            icon="CHECKMARK",
        )

        if implementation is not None:
            descriptor = (
                implementation
                .descriptor
            )

            if descriptor.capabilities:
                capabilities = (
                    layout.box()
                )

                capabilities.label(
                    text="Capabilities",
                    icon="INFO",
                )

                for capability in (
                    descriptor.capabilities
                ):
                    capabilities.label(
                        text=capability,
                    )

        defaults = (
            layout.box()
        )

        defaults.label(
            text="Current Defaults",
            icon="SETTINGS",
        )

        defaults.label(
            text=(
                "Min facing: 0.10"
            )
        )

        defaults.label(
            text=(
                "Relative cutoff: 0.20"
            )
        )

        defaults.label(
            text=(
                "Max contributors: 3"
            )
        )

        defaults.label(
            text=(
                "Weight power: 1.5"
            )
        )

    # -----------------------------------------------------
    # Stage action
    # -----------------------------------------------------

    def _draw_stage_action(
        self,
        layout,
        stage: PipelineStage,
        stage_settings,
        descriptors,
    ) -> None:
        if not descriptors:
            return

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if not implementation_id:
            return

        row = (
            layout.row()
        )

        row.enabled = (
            stage_settings.enabled
            and (
                _descriptor_for_selection(
                    stage,
                    implementation_id,
                )
                is not None
            )
        )

        row.scale_y = 1.15

        operator = (
            row.operator(
                "bpt.run_pipeline_stage",
                text=(
                    STAGE_RUN_LABELS
                    .get(
                        stage,
                        "Run Stage",
                    )
                ),
                icon="PLAY",
            )
        )

        operator.stage = (
            stage.value
        )

    # -----------------------------------------------------
    # Generate all
    # -----------------------------------------------------

    def _draw_generate_all(
        self,
        layout,
        settings,
    ) -> None:
        box = (
            layout.box()
        )

        row = (
            box.row()
        )

        row.scale_y = 1.8

        row.operator(
            "bpt.run_pipeline",
            text="GENERATE ALL",
            icon="PLAY",
        )

        enabled_labels = []

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            current = (
                pipeline_stage_settings(
                    settings,
                    stage,
                )
            )

            if (
                current.enabled
                and current
                .implementation_id
                .strip()
            ):
                enabled_labels.append(
                    stage_spec(
                        stage
                    )
                    .label
                )

        if enabled_labels:
            box.label(
                text=(
                    " → ".join(
                        enabled_labels
                    )
                ),
                icon="INFO",
            )

    # -----------------------------------------------------
    # Last pipeline run
    # -----------------------------------------------------

    def _draw_last_run(
        self,
        layout,
        context: bpy.types.Context,
        settings,
    ) -> None:
        pipeline = (
            settings.pipeline
        )

        box = (
            layout.box()
        )

        header = (
            box.row(
                align=True
            )
        )

        header.prop(
            pipeline,
            "diagnostics_expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if (
                    pipeline
                    .diagnostics_expanded
                )
                else "TRIA_RIGHT"
            ),
        )

        header.label(
            text="Last Run",
            icon="INFO",
        )

        report = (
            get_last_pipeline_report(
                context.scene
            )
        )

        if report is None:
            status = (
                header.row()
            )

            status.alignment = (
                "RIGHT"
            )

            status.label(
                text="None",
            )

            if (
                pipeline
                .diagnostics_expanded
            ):
                box.label(
                    text=(
                        "No pipeline execution yet."
                    ),
                    icon="INFO",
                )

            return

        status = (
            header.row()
        )

        status.alignment = (
            "RIGHT"
        )

        status.alert = (
            not report.success
        )

        status.label(
            text=(
                "Success"
                if report.success
                else "Failed"
            ),
            icon=(
                "CHECKMARK"
                if report.success
                else "ERROR"
            ),
        )

        if not (
            pipeline
            .diagnostics_expanded
        ):
            return

        summary = (
            box.row()
        )

        summary.label(
            text=(
                f"{report.duration_seconds:.3f}s"
            ),
            icon="TIME",
        )

        for record in (
            report.records
        ):
            stage_box = (
                box.box()
            )

            row = (
                stage_box.row()
            )

            row.label(
                text=(
                    stage_spec(
                        record.stage
                    )
                    .label
                ),
                icon=(
                    STAGE_ICONS[
                        record.stage
                    ]
                ),
            )

            state = (
                row.row()
            )

            state.alignment = (
                "RIGHT"
            )

            state.alert = (
                record.failed
            )

            state.label(
                text=(
                    record
                    .result
                    .state
                    .value
                    .title()
                ),
                icon=(
                    "CHECKMARK"
                    if record.success
                    else (
                        "ERROR"
                        if record.failed
                        else "INFO"
                    )
                ),
            )

            if (
                record.result.message
            ):
                _draw_wrapped_text(
                    stage_box,
                    record
                    .result
                    .message,
                    width=38,
                )

            stage_box.label(
                text=(
                    f"{record.duration_seconds:.3f}s"
                ),
                icon="TIME",
            )

    # -----------------------------------------------------
    # Advanced
    # -----------------------------------------------------

    def _draw_advanced(
        self,
        layout,
        context: bpy.types.Context,
        settings,
    ) -> None:
        pipeline = (
            settings.pipeline
        )

        box = (
            layout.box()
        )

        header = (
            box.row(
                align=True
            )
        )

        header.prop(
            pipeline,
            "advanced_expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if (
                    pipeline
                    .advanced_expanded
                )
                else "TRIA_RIGHT"
            ),
        )

        header.label(
            text="Advanced",
            icon="PREFERENCES",
        )

        if not (
            pipeline
            .advanced_expanded
        ):
            return

        registry = (
            box.box()
        )

        registry.label(
            text="Pipeline Registry",
            icon="SETTINGS",
        )

        registry.label(
            text=(
                f"{len(PIPELINE_REGISTRY)} "
                "implementations registered"
            )
        )

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            stage_settings = (
                pipeline_stage_settings(
                    settings,
                    stage,
                )
            )

            row = (
                registry.row()
            )

            row.label(
                text=(
                    stage_spec(
                        stage
                    )
                    .label
                ),
                icon=(
                    STAGE_ICONS[
                        stage
                    ]
                ),
            )

            value = (
                row.row()
            )

            value.alignment = (
                "RIGHT"
            )

            implementation_id = (
                stage_settings
                .implementation_id
                .strip()
            )

            value.label(
                text=(
                    implementation_id
                    or "—"
                )
            )

        box.separator()

        reset = (
            box.row()
        )

        reset.operator(
            "bpt.reset_pipeline_settings",
            text="Reset Pipeline Configuration",
            icon="FILE_REFRESH",
        )


# ---------------------------------------------------------
# Classes
# ---------------------------------------------------------

CLASSES = (
    BPT_UL_ProjectionViews,
    BPT_PT_MainPanel,
)


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

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