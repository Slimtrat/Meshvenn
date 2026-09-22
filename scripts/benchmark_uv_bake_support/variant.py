from __future__ import annotations

from .shared import BenchmarkVariant, Path, RunLogger, UV_IMPLEMENTATION_ID, argparse, build_geometry_output, build_material_settings, cleanup_object, clear_scene, create_blender_mesh_from_native, execute_material, export_object, scale_object_to_height, shade_smooth_native_object
from .artifacts import write_json
from .material import material_diagnostics, save_baked_texture

def variant_args(
    args: argparse.Namespace,
    *,
    texture_size: int,
) -> argparse.Namespace:
    values = dict(
        vars(
            args
        )
    )

    values[
        "texture_size"
    ] = (
        texture_size
    )

    return argparse.Namespace(
        **values
    )

def generate_variant(
    runtime,
    *,
    sheet_name: str,
    profile: str,
    implementation_id: str,
    texture_size: int,
    snapshot,
    source,
    variant_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> BenchmarkVariant:
    clear_scene()

    obj = None

    try:
        name = (
            "MeshvennBenchmark_"
            f"{sheet_name}_"
            f"{profile}_"
            f"{implementation_id}_"
            f"{texture_size}"
        )

        obj = (
            create_blender_mesh_from_native(
                snapshot.mesh,
                mesh_name=name,
                object_name=name,
            )
        )

        shade_smooth_native_object(
            obj
        )

        local_args = (
            variant_args(
                args,
                texture_size=(
                    texture_size
                ),
            )
        )

        geometry = (
            build_geometry_output(
                runtime,

                obj=obj,

                snapshot=snapshot,

                source=source,

                args=local_args,
            )
        )

        settings = (
            build_material_settings(
                local_args
            )
        )

        (
            result,
            material_seconds,
            availability,
        ) = (
            execute_material(
                runtime,

                implementation_id=(
                    implementation_id
                ),

                geometry=geometry,

                settings=settings,
            )
        )

        # Projection coordinates must stay native until
        # MATERIAL execution has finished.
        scale_object_to_height(
            obj,
            args.target_height,
        )

        obj[
            "meshvenn_benchmark"
        ] = True

        obj[
            "meshvenn_benchmark_sheet"
        ] = sheet_name

        obj[
            "meshvenn_benchmark_profile"
        ] = profile

        obj[
            "meshvenn_benchmark_material"
        ] = implementation_id

        obj[
            "meshvenn_benchmark_texture_size"
        ] = texture_size

        variant_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        texture_png = (
            save_baked_texture(
                result.payload,

                variant_root
                / "baked_texture.png",
            )
        )

        export_info = (
            export_object(
                obj,

                output_dir=(
                    variant_root
                ),

                stem="model",

                save_blend=bool(
                    args.save_blend
                ),
            )
        )

        model_path = (
            variant_root
            / "model.glb"
        )

        if not model_path.is_file():
            raise RuntimeError(
                (
                    "GLB export did not "
                    "produce model.glb."
                )
            )

        diagnostics = (
            material_diagnostics(
                result
            )
        )

        info = {
            "generated": True,

            "sheet": (
                sheet_name
            ),

            "profile": (
                profile
            ),

            "implementation": (
                implementation_id
            ),

            "texture_size": (
                texture_size
                if (
                    implementation_id
                    == UV_IMPLEMENTATION_ID
                )
                else None
            ),

            "material_seconds": (
                material_seconds
            ),

            "availability": {
                "state": (
                    availability
                    .state
                    .value
                ),

                "reason": (
                    availability.reason
                ),

                "details": (
                    availability.details
                ),
            },

            "result": {
                "message": (
                    result.message
                ),

                "metrics": (
                    result.metrics
                ),

                "metadata": (
                    result.metadata
                ),
            },

            "geometry": {
                "vertices": len(
                    obj.data.vertices
                ),

                "faces": len(
                    obj.data.polygons
                ),

                "dimensions": [
                    float(
                        value
                    )
                    for value
                    in obj.dimensions
                ],

                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),

                "mesh_mode": (
                    args.mesh_mode
                ),

                "resolution": (
                    args.resolution
                ),
            },

            **diagnostics,

            "texture_png": (
                str(
                    texture_png
                )
                if texture_png
                is not None
                else None
            ),

            "texture_png_bytes": (
                texture_png
                .stat()
                .st_size
                if texture_png
                is not None
                else None
            ),

            "export": (
                export_info
            ),

            "glb_bytes": (
                model_path
                .stat()
                .st_size
            ),
        }

        manifest_path = (
            variant_root
            / "variant.json"
        )

        write_json(
            manifest_path,
            info,
        )

        return BenchmarkVariant(
            sheet=(
                sheet_name
            ),

            profile=(
                profile
            ),

            implementation=(
                implementation_id
            ),

            texture_size=(
                texture_size
                if (
                    implementation_id
                    == UV_IMPLEMENTATION_ID
                )
                else None
            ),

            root=(
                variant_root
            ),

            model_path=(
                model_path
            ),

            manifest_path=(
                manifest_path
            ),

            render_root=(
                variant_root
                / "render"
            ),

            contact_sheet_path=(
                variant_root
                / "render"
                / "contact_sheet.png"
            ),

            info=(
                info
            ),
        )

    finally:
        cleanup_object(
            obj
        )
