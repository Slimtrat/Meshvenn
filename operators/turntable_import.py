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

from ..core.pipeline_contracts import (
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
)
from ..core.pipeline_registry import PIPELINE_REGISTRY
from ..core.pipeline_runner import (
    PipelineExecutionReport,
    PipelineRunOptions,
    PipelineRunner,
)
from ..properties import (
    build_pipeline_plan,
    pipeline_stage_settings,
    reset_pipeline_defaults,
    set_pipeline_implementation,
)

from .constants import ANGLE_PATTERN, IMAGE_FILTER
from .runtime import clear_pipeline_runtime_state
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
