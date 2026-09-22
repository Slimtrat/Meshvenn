#include "surface_nets_internal.h"

#include <new>
// ---------------------------------------------------------
// Internal entry point
// ---------------------------------------------------------

namespace bpt_internal
{
using surface_nets_detail::SurfaceNetsBuilder;
using surface_nets_detail::copy_to_result;
using surface_nets_detail::create_cell_grid;
using surface_nets_detail::generate_cell_vertices;
using surface_nets_detail::generate_x_edge_quads;
using surface_nets_detail::generate_y_edge_quads;
using surface_nets_detail::generate_z_edge_quads;


BptResultCode
build_surface_nets_mesh(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
)
{
    if (
        volume == nullptr
        || options == nullptr
        || out_mesh == nullptr
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    /*
     * mesh.cpp already validates these inputs before
     * dispatching here, but retain the basic checks so
     * this backend stays safe if reused internally later.
     */
    if (
        options->voxel_size <= 0.0f
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        volume->occupied_count == 0
        || volume->has_bounds == 0
    )
    {
        *out_mesh =
            BptMeshResult {};

        return BPT_OK;
    }

    try
    {
        SurfaceNetsBuilder builder;

        /*
         * Rough reservation only.
         *
         * Surface Nets usually generates dramatically fewer
         * polygons than one face per exposed voxel side.
         */
        builder.indices.reserve(
            volume->occupied_count
            * 8
        );

        builder.polygon_starts.reserve(
            volume->occupied_count
            * 2
        );

        builder.polygon_sizes.reserve(
            volume->occupied_count
            * 2
        );

        auto grid =
            create_cell_grid(
                *volume
            );

        if (
            grid.vertices.empty()
        )
        {
            *out_mesh =
                BptMeshResult {};

            return BPT_OK;
        }

        // -------------------------------------------------
        // Pass 1
        //
        // One vertex per active boundary cell.
        // -------------------------------------------------

        generate_cell_vertices(
            *volume,
            *options,
            grid,
            builder
        );

        if (
            builder.vertices.empty()
        )
        {
            *out_mesh =
                BptMeshResult {};

            return BPT_OK;
        }

        // -------------------------------------------------
        // Pass 2
        //
        // Every sign-changing sample edge connects the
        // four surrounding active cells.
        // -------------------------------------------------

        auto result =
            generate_x_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        result =
            generate_y_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        result =
            generate_z_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        copy_to_result(
            builder,
            out_mesh
        );

        return BPT_OK;
    }
    catch (
        const std::bad_alloc&
    )
    {
        bpt_free_mesh(
            out_mesh
        );

        return (
            BPT_ERROR_ALLOCATION_FAILED
        );
    }
    catch (...)
    {
        bpt_free_mesh(
            out_mesh
        );

        return (
            BPT_ERROR_INTERNAL
        );
    }
}


} // namespace bpt_internal
