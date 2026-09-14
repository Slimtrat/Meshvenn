from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import bpy

from .constants import *
from .support import (
    _load_extension, _operator_available, _operator_callable,
    _operator_rna_class, _panel_rna_class, _parse_arguments,
    _purge_package_modules, _require, _require_close, _section,
    _ui_list_rna_class, _validate_package_tree,
)

# Generic GEOMETRY -> MATERIAL compatibility
# =========================================================

def _validate_generic_geometry_material_compatibility(
    package_name: str,
    settings,
) -> None:
    """
    Use a real Blender mesh wrapped only in
    GeometrySurfaceOutput.

    It deliberately exposes no:

        NativeVolume
        NativeMesh
        SDFBuildResult
        SDFSurfaceResult

    Both MATERIAL implementations must accept it.
    """

    _section(
        "generic GEOMETRY -> MATERIAL"
    )

    geometry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.geometry_contracts"
            )
        )
    )

    contracts_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_contracts"
            )
        )
    )

    registry_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "core.pipeline_registry"
            )
        )
    )

    native_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "native_visual_hull"
            )
        )
    )

    sdf_module = (
        importlib.import_module(
            (
                f"{package_name}."
                "implementations."
                "sdf_reconstruction"
            )
        )
    )

    GeometryProjectionSpace = (
        geometry_module
        .GeometryProjectionSpace
    )

    GeometrySurfaceOutput = (
        geometry_module
        .GeometrySurfaceOutput
    )

    PipelineContext = (
        contracts_module
        .PipelineContext
    )

    PipelineStage = (
        contracts_module
        .PipelineStage
    )

    mesh = None
    obj = None

    try:
        mesh = (
            bpy.data.meshes.new(
                "Meshvenn Generic Geometry Smoke Mesh"
            )
        )

        mesh.from_pydata(
            [
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                (
                    1.0,
                    0.0,
                    0.0,
                ),
                (
                    0.0,
                    1.0,
                    0.0,
                ),
            ],
            [],
            [
                (
                    0,
                    1,
                    2,
                )
            ],
        )

        mesh.update()

        obj = (
            bpy.data.objects.new(
                (
                    "Meshvenn Generic "
                    "Geometry Smoke Object"
                ),
                mesh,
            )
        )

        scene = (
            bpy.context.scene
        )

        scene.collection.objects.link(
            obj
        )

        fake_source = (
            SimpleNamespace(
                material_views=(
                    object(),
                    object(),
                )
            )
        )

        projection_space = (
            GeometryProjectionSpace(
                width=16,
                depth=16,
                height=16,
                voxel_size=1.0,
                center_xy=True,
            )
        )

        geometry_output = (
            GeometrySurfaceOutput(
                blender_object=obj,
                source=fake_source,
                projection_space=(
                    projection_space
                ),
                implementation_id=(
                    FAKE_GEOMETRY_IMPLEMENTATION_ID
                ),
                metrics={
                    "vertex_count":
                        len(
                            mesh.vertices
                        ),

                    "polygon_count":
                        len(
                            mesh.polygons
                        ),
                },
            )
        )

        _require(
            not isinstance(
                geometry_output,
                native_module
                .NativeVisualHullOutput,
            ),
            (
                "Generic test accidentally "
                "uses NativeVisualHullOutput."
            ),
        )

        _require(
            not isinstance(
                geometry_output,
                sdf_module
                .SDFReconstructionOutput,
            ),
            (
                "Generic test accidentally "
                "uses SDFReconstructionOutput."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "volume",
            ),
            (
                "Generic geometry exposes "
                "native volume."
            ),
        )

        _require(
            not hasattr(
                geometry_output,
                "sdf_result",
            ),
            (
                "Generic geometry exposes "
                "SDF internals."
            ),
        )

        context = (
            PipelineContext(
                scene=scene,
                settings=settings,
            )
        )

        context.set_output(
            PipelineStage.GEOMETRY,
            geometry_output,
        )

        projected = (
            registry_module
            .PIPELINE_REGISTRY
            .require(
                "projected-color-v1.2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        projected_status = (
            projected.availability(
                context
            )
        )

        _require(
            projected_status.ready,
            (
                "Projected Color rejected "
                "generic geometry.\n"
                f"{projected_status.reason}"
            ),
        )

        uv_bake = (
            registry_module
            .PIPELINE_REGISTRY
            .require(
                "uv-bake-v2",
                stage=(
                    PipelineStage.MATERIAL
                ),
            )
        )

        uv_status = (
            uv_bake.availability(
                context
            )
        )

        _require(
            uv_status.ready,
            (
                "UV Bake rejected "
                "generic geometry.\n"
                f"{uv_status.reason}"
            ),
        )

        _require(
            projected_status
            .details
            .get(
                "geometry_implementation"
            )
            == FAKE_GEOMETRY_IMPLEMENTATION_ID,
            (
                "Projected Color lost "
                "generic geometry identity."
            ),
        )

        _require(
            uv_status
            .details
            .get(
                "geometry_implementation"
            )
            == FAKE_GEOMETRY_IMPLEMENTATION_ID,
            (
                "UV Bake lost "
                "generic geometry identity."
            ),
        )

        print(
            "Generic GEOMETRY compatibility: OK"
        )

        print(
            "  projected-color-v1.2: READY"
        )

        print(
            "  uv-bake-v2:             READY"
        )

    finally:
        if obj is not None:
            try:
                bpy.data.objects.remove(
                    obj,
                    do_unlink=True,
                )

            except Exception:
                pass

        if (
            mesh is not None
            and mesh.users == 0
        ):
            try:
                bpy.data.meshes.remove(
                    mesh
                )

            except Exception:
                pass
