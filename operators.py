from __future__ import annotations

import math
import os
import re

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from .core.pipeline_contracts import (
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
)
from .core.pipeline_registry import (
    PIPELINE_REGISTRY,
)
from .core.pipeline_runner import (
    PipelineExecutionReport,
    PipelineRunOptions,
    PipelineRunner,
)
from .properties import (
    build_pipeline_plan,
    pipeline_stage_settings,
    reset_pipeline_defaults,
    set_pipeline_implementation,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

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


PIPELINE_STAGE_ENUM_ITEMS = (
    (
        PipelineStage.INPUT.value,
        "Input",
        "Input preparation stage",
    ),
    (
        PipelineStage.GEOMETRY.value,
        "Geometry",
        "3D geometry reconstruction stage",
    ),
    (
        PipelineStage.MATERIAL.value,
        "Material",
        "Material generation stage",
    ),
    (
        PipelineStage.RIG.value,
        "Rig",
        "Rig generation stage",
    ),
    (
        PipelineStage.EXPORT.value,
        "Export",
        "Asset export stage",
    ),
)


RUNNABLE_STAGE_ENUM_ITEMS = (
    (
        PipelineStage.GEOMETRY.value,
        "Geometry",
        (
            "Run the pipeline through "
            "the Geometry stage"
        ),
    ),
    (
        PipelineStage.MATERIAL.value,
        "Material",
        (
            "Run the pipeline through "
            "the Material stage"
        ),
    ),
    (
        PipelineStage.RIG.value,
        "Rig",
        (
            "Run the pipeline through "
            "the Rig stage"
        ),
    ),
    (
        PipelineStage.EXPORT.value,
        "Export",
        (
            "Run the pipeline through "
            "the Export stage"
        ),
    ),
)


# ---------------------------------------------------------
# Runtime state
#
# Blender PropertyGroups store persistent configuration.
#
# Execution reports are runtime objects and should not be
# serialized into the .blend file wholesale.
#
# A lightweight summary is mirrored into Scene custom
# properties for diagnostics.
# ---------------------------------------------------------

_LAST_PIPELINE_REPORTS: dict[
    int,
    PipelineExecutionReport,
] = {}


_LAST_PIPELINE_CONTEXTS: dict[
    int,
    PipelineContext,
] = {}


def _scene_key(
    scene: bpy.types.Scene,
) -> int:
    return int(
        scene.as_pointer()
    )


def get_last_pipeline_report(
    scene: bpy.types.Scene,
) -> (
    PipelineExecutionReport
    | None
):
    """
    Runtime accessor intended for ui.py.
    """

    return (
        _LAST_PIPELINE_REPORTS
        .get(
            _scene_key(
                scene
            )
        )
    )


def get_last_pipeline_context(
    scene: bpy.types.Scene,
) -> (
    PipelineContext
    | None
):
    return (
        _LAST_PIPELINE_CONTEXTS
        .get(
            _scene_key(
                scene
            )
        )
    )


def clear_pipeline_runtime_state(
    scene: (
        bpy.types.Scene
        | None
    ) = None,
) -> None:
    if scene is None:
        _LAST_PIPELINE_REPORTS.clear()
        _LAST_PIPELINE_CONTEXTS.clear()

        return

    key = (
        _scene_key(
            scene
        )
    )

    _LAST_PIPELINE_REPORTS.pop(
        key,
        None,
    )

    _LAST_PIPELINE_CONTEXTS.pop(
        key,
        None,
    )


# ---------------------------------------------------------
# Pipeline report helpers
# ---------------------------------------------------------

def _pipeline_failure_message(
    report: PipelineExecutionReport,
) -> str:
    message = (
        report
        .failure_message
        .strip()
    )

    if not message:
        return (
            "Pipeline execution failed."
        )

    # Blender status reports are easier to read when kept
    # to one line. Complete details remain in the runtime
    # PipelineExecutionReport.
    first_line = (
        message
        .splitlines()[0]
        .strip()
    )

    return (
        first_line
        or "Pipeline execution failed."
    )


def _pipeline_success_message(
    report: PipelineExecutionReport,
) -> str:
    successful = (
        report
        .successful_records
    )

    if successful:
        message = (
            successful[-1]
            .result
            .message
            .strip()
        )

        if message:
            return message

    stage_count = len(
        successful
    )

    return (
        "Meshvenn pipeline completed "
        f"with {stage_count} successful stage"
        + (
            "s."
            if stage_count != 1
            else "."
        )
    )


def _store_pipeline_runtime(
    scene: bpy.types.Scene,
    pipeline_context: PipelineContext,
    report: PipelineExecutionReport,
) -> None:
    key = (
        _scene_key(
            scene
        )
    )

    _LAST_PIPELINE_CONTEXTS[
        key
    ] = (
        pipeline_context
    )

    _LAST_PIPELINE_REPORTS[
        key
    ] = (
        report
    )

    # -----------------------------------------------------
    # Lightweight persistent diagnostic snapshot.
    # -----------------------------------------------------

    scene[
        "meshvenn_last_pipeline_status"
    ] = (
        "success"
        if report.success
        else "failed"
    )

    scene[
        "meshvenn_last_pipeline_duration"
    ] = float(
        report.duration_seconds
    )

    scene[
        "meshvenn_last_pipeline_aborted"
    ] = bool(
        report.aborted
    )

    scene[
        "meshvenn_last_pipeline_stage_count"
    ] = len(
        report.records
    )

    scene[
        "meshvenn_last_pipeline_successful_stages"
    ] = len(
        report.successful_records
    )

    scene[
        "meshvenn_last_pipeline_failed_stages"
    ] = len(
        report.failed_records
    )

    if report.success:
        scene[
            "meshvenn_last_pipeline_message"
        ] = (
            _pipeline_success_message(
                report
            )
        )

    else:
        scene[
            "meshvenn_last_pipeline_message"
        ] = (
            _pipeline_failure_message(
                report
            )
        )

    if report.records:
        scene[
            "meshvenn_last_pipeline_last_stage"
        ] = (
            report
            .records[-1]
            .stage
            .value
        )

    else:
        scene[
            "meshvenn_last_pipeline_last_stage"
        ] = ""


def _new_pipeline_context(
    context: bpy.types.Context,
) -> PipelineContext:
    scene = (
        context.scene
    )

    if scene is None:
        raise RuntimeError(
            "No active Blender scene."
        )

    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    if settings is None:
        raise RuntimeError(
            "Meshvenn settings are unavailable."
        )

    return (
        PipelineContext(
            scene=scene,
            settings=settings,
            metadata={
                "source": "blender-ui",
            },
        )
    )


def _execute_pipeline_plan(
    operator: Operator,
    context: bpy.types.Context,
    plan: PipelinePlan,
) -> set[str]:
    """
    Common Blender -> PipelineRunner boundary.

    All generation operators must pass through here instead
    of invoking concrete implementations themselves.
    """

    scene = (
        context.scene
    )

    if scene is None:
        operator.report(
            {"ERROR"},
            "No active Blender scene.",
        )

        return {
            "CANCELLED"
        }

    try:
        pipeline_context = (
            _new_pipeline_context(
                context
            )
        )

        runner = (
            PipelineRunner(
                PIPELINE_REGISTRY
            )
        )

        report = (
            runner.run(
                plan,
                pipeline_context,
                options=(
                    PipelineRunOptions(
                        stop_on_failure=True,
                        catch_exceptions=True,
                        check_availability=True,
                    )
                ),
            )
        )

    except Exception as exc:
        operator.report(
            {"ERROR"},
            (
                "Pipeline could not start: "
                f"{exc}"
            ),
        )

        return {
            "CANCELLED"
        }

    _store_pipeline_runtime(
        scene,
        pipeline_context,
        report,
    )

    if not report.success:
        operator.report(
            {"ERROR"},
            _pipeline_failure_message(
                report
            ),
        )

        return {
            "CANCELLED"
        }

    operator.report(
        {"INFO"},
        _pipeline_success_message(
            report
        ),
    )

    return {
        "FINISHED"
    }


# ---------------------------------------------------------
# Pipeline plan helpers
# ---------------------------------------------------------

def _plan_through_stage(
    settings,
    target_stage: PipelineStage,
) -> PipelinePlan:
    """
    Build a deterministic pipeline prefix.

    Example:

        target = GEOMETRY

            INPUT
            GEOMETRY

        target = MATERIAL

            INPUT
            GEOMETRY
            MATERIAL

        target = RIG

            INPUT
            GEOMETRY
            MATERIAL if configured
            RIG

    Disabled stages remain disabled in the plan. This keeps
    the user's persistent pipeline configuration authoritative.
    """

    full_plan = (
        build_pipeline_plan(
            settings
        )
    )

    target_selection = (
        full_plan
        .selection_for(
            target_stage
        )
    )

    if target_selection is None:
        raise ValueError(
            (
                f'Pipeline stage "{target_stage.value}" '
                "has no implementation selected."
            )
        )

    if not target_selection.enabled:
        raise ValueError(
            (
                f'Pipeline stage "{target_stage.value}" '
                "is disabled."
            )
        )

    target_index = (
        PIPELINE_STAGE_ORDER
        .index(
            target_stage
        )
    )

    selections = tuple(
        selection
        for selection
        in full_plan.selections
        if (
            PIPELINE_STAGE_ORDER
            .index(
                selection.stage
            )
            <= target_index
        )
    )

    return (
        PipelinePlan(
            selections=(
                selections
            )
        )
    )


# ---------------------------------------------------------
# Image loading
# ---------------------------------------------------------

class BPT_OT_LoadProjectionImage(
    Operator,
    ImportHelper,
):
    bl_idname = (
        "bpt.load_projection_image"
    )

    bl_label = (
        "Load Projection Image"
    )

    bl_description = (
        "Load an image from disk and assign it "
        "to the selected projection"
    )

    filename_ext = ".png"

    filter_glob: StringProperty(
        default=IMAGE_FILTER,
        options={
            "HIDDEN",
        },
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
            context
            .scene
            .bpt_settings
        )

        if (
            self.index < 0
            or self.index
            >= len(
                settings.projections
            )
        ):
            self.report(
                {"ERROR"},
                "Invalid projection index.",
            )

            return {
                "CANCELLED"
            }

        try:
            image = (
                bpy.data
                .images
                .load(
                    self.filepath,
                    check_existing=True,
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not load image: "
                    f"{exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        settings.projections[
            self.index
        ].image = (
            image
        )

        settings.active_projection_index = (
            self.index
        )

        # Prepared INPUT data from a previous run is now
        # potentially stale.
        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            (
                f'Loaded image "{image.name}".'
            ),
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
        options={
            "HIDDEN",
        },
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
            context
            .scene
            .bpt_settings
        )

        selected_files = (
            self
            ._collect_selected_files()
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
            entries = (
                self
                ._build_entries(
                    selected_files
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Image import failed: "
                    f"{exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        if self.clear_existing:
            settings.projections.clear()

        for entry in entries:
            projection = (
                settings
                .projections
                .add()
            )

            projection.name = (
                entry[
                    "name"
                ]
            )

            projection.azimuth = (
                math.radians(
                    entry[
                        "angle_deg"
                    ]
                )
            )

            projection.elevation = 0.0

            projection.enabled = True

            projection.flip_x = False

            projection.image = (
                entry[
                    "image"
                ]
            )

        settings.active_projection_index = 0

        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            (
                f"Imported "
                f"{len(entries)} "
                "projection images."
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
            image = (
                bpy.data
                .images
                .load(
                    filepath,
                    check_existing=True,
                )
            )

            stem = (
                os.path
                .splitext(
                    os.path.basename(
                        filepath
                    )
                )[0]
            )

            angle = (
                _extract_angle_from_name(
                    stem
                )
            )

            loaded.append(
                {
                    "filepath": (
                        filepath
                    ),
                    "stem": (
                        stem
                    ),
                    "image": (
                        image
                    ),
                    "angle_deg": (
                        angle
                    ),
                }
            )

        # -------------------------------------------------
        # If one or more filenames do not expose an angle,
        # assign missing angles using an evenly-spaced
        # turntable.
        # -------------------------------------------------

        if any(
            item[
                "angle_deg"
            ] is None
            for item
            in loaded
        ):
            step = (
                360.0
                / max(
                    len(
                        loaded
                    ),
                    1,
                )
            )

            for (
                index,
                item,
            ) in enumerate(
                loaded
            ):
                if (
                    item[
                        "angle_deg"
                    ]
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
                item[
                    "angle_deg"
                ]
            )
        )

        entries = []

        for item in loaded:
            angle = (
                float(
                    item[
                        "angle_deg"
                    ]
                )
                % 360.0
            )

            entries.append(
                {
                    "name": (
                        f"{angle:.1f}° "
                        f"- "
                        f"{item['stem']}"
                    ),
                    "angle_deg": (
                        angle
                    ),
                    "image": (
                        item[
                            "image"
                        ]
                    ),
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
    bl_idname = (
        "bpt.add_projection"
    )

    bl_label = (
        "Add Projection"
    )

    bl_description = (
        "Add a new arbitrary projection view"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        projection = (
            settings
            .projections
            .add()
        )

        projection.name = (
            "Projection "
            f"{len(settings.projections)}"
        )

        projection.azimuth = 0.0

        projection.elevation = 0.0

        projection.enabled = True

        projection.flip_x = False

        settings.active_projection_index = (
            len(
                settings.projections
            )
            - 1
        )

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


class BPT_OT_RemoveProjection(
    Operator
):
    bl_idname = (
        "bpt.remove_projection"
    )

    bl_label = (
        "Remove Projection"
    )

    bl_description = (
        "Remove the selected projection"
    )

    index: IntProperty()

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
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

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Projection presets
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
            context
            .scene
            .bpt_settings
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

        clear_pipeline_runtime_state(
            context.scene
        )

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
            context
            .scene
            .bpt_settings
        )

        settings.projections.clear()

        front = (
            settings
            .projections
            .add()
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
            settings
            .projections
            .add()
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

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Generic pipeline implementation selection
# ---------------------------------------------------------

class BPT_OT_SetPipelineImplementation(
    Operator
):
    """
    Generic implementation-selection action.

    ui.py can create one of these buttons for every
    ImplementationDescriptor exposed by PIPELINE_REGISTRY.

    No algorithm-specific operator is required.
    """

    bl_idname = (
        "bpt.set_pipeline_implementation"
    )

    bl_label = (
        "Select Implementation"
    )

    bl_description = (
        "Select the implementation used "
        "for a pipeline stage"
    )

    stage: EnumProperty(
        name="Stage",
        items=(
            PIPELINE_STAGE_ENUM_ITEMS
        ),
        default=(
            PipelineStage.GEOMETRY.value
        ),
    )

    implementation_id: StringProperty(
        name="Implementation",
        default="",
    )

    enable_stage: BoolProperty(
        name="Enable Stage",
        default=True,
        options={
            "HIDDEN",
        },
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        try:
            stage = (
                PipelineStage(
                    self.stage
                )
            )

            implementation_id = (
                self
                .implementation_id
                .strip()
            )

            if not implementation_id:
                raise ValueError(
                    (
                        "Implementation id "
                        "cannot be empty."
                    )
                )

            implementation = (
                PIPELINE_REGISTRY
                .require(
                    implementation_id,
                    stage=stage,
                )
            )

            set_pipeline_implementation(
                settings,
                stage,
                implementation
                .descriptor
                .identifier,
            )

            if self.enable_stage:
                stage_settings = (
                    pipeline_stage_settings(
                        settings,
                        stage,
                    )
                )

                stage_settings.enabled = True

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not select "
                    f"implementation: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            (
                f"{stage.value.title()}: "
                f"{implementation.descriptor.label}"
            ),
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Pipeline reset
# ---------------------------------------------------------

class BPT_OT_ResetPipelineSettings(
    Operator
):
    bl_idname = (
        "bpt.reset_pipeline_settings"
    )

    bl_label = (
        "Reset Pipeline"
    )

    bl_description = (
        "Reset pipeline stage selections "
        "without deleting projection images "
        "or generation parameters"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        reset_pipeline_defaults(
            settings
        )

        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            "Pipeline settings reset.",
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Complete pipeline
# ---------------------------------------------------------

class BPT_OT_RunPipeline(
    Operator
):
    """
    Main Meshvenn product action.

    Blender
        ↓
    PipelinePlan
        ↓
    PipelineRunner
        ↓
    PIPELINE_REGISTRY
        ↓
    concrete implementations
    """

    bl_idname = (
        "bpt.run_pipeline"
    )

    bl_label = (
        "Generate"
    )

    bl_description = (
        "Run the configured Meshvenn pipeline"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        try:
            plan = (
                build_pipeline_plan(
                    settings
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Invalid pipeline "
                    f"configuration: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Run pipeline through one stage
# ---------------------------------------------------------

class BPT_OT_RunPipelineStage(
    Operator
):
    """
    Run the pipeline up to a selected stage.

    This deliberately rebuilds required upstream stages.

    Example:

        Run Geometry

            INPUT
              ↓
            GEOMETRY

        Run Material

            INPUT
              ↓
            GEOMETRY
              ↓
            MATERIAL

    This makes stage execution deterministic for the first
    general UI version.

    Incremental reuse of previous stage outputs can be added
    later without changing the UI contract.
    """

    bl_idname = (
        "bpt.run_pipeline_stage"
    )

    bl_label = (
        "Run Stage"
    )

    bl_description = (
        "Run the configured pipeline "
        "through this stage"
    )

    stage: EnumProperty(
        name="Stage",
        items=(
            RUNNABLE_STAGE_ENUM_ITEMS
        ),
        default=(
            PipelineStage.GEOMETRY.value
        ),
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        try:
            stage = (
                PipelineStage(
                    self.stage
                )
            )

            plan = (
                _plan_through_stage(
                    settings,
                    stage,
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not run "
                    f"{self.stage}: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------

class BPT_OT_GenerateCharacter(
    Operator
):
    """
    Compatibility alias.

    Existing UI/scripts may still invoke:

        bpy.ops.bpt.generate_character()

    It now executes the exact same generic pipeline as:

        bpy.ops.bpt.run_pipeline()

    No reconstruction implementation exists in this
    operator anymore.
    """

    bl_idname = (
        "bpt.generate_character"
    )

    bl_label = (
        "Generate Scan"
    )

    bl_description = (
        "Compatibility alias for the "
        "Meshvenn generation pipeline"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        try:
            plan = (
                build_pipeline_plan(
                    settings
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Invalid pipeline "
                    f"configuration: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Filename angle detection
# ---------------------------------------------------------

def _extract_angle_from_name(
    name: str,
) -> float | None:
    match = (
        ANGLE_PATTERN
        .search(
            name
        )
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

    BPT_OT_SetPipelineImplementation,

    BPT_OT_ResetPipelineSettings,

    BPT_OT_RunPipeline,

    BPT_OT_RunPipelineStage,

    BPT_OT_GenerateCharacter,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )


def unregister() -> None:
    clear_pipeline_runtime_state()

    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )