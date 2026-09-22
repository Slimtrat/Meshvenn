#include "bpt_core.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <new>
#include <unordered_map>
#include <utility>
#include <vector>


// ---------------------------------------------------------
// Surface Nets backend
// ---------------------------------------------------------
//
// Implemented in surface_nets.cpp.
//
// This is intentionally not part of the public C ABI.
// bpt_build_surface_mesh_ex() remains the only public
// dispatch point.
// ---------------------------------------------------------

namespace bpt_internal
{


BptResultCode
build_surface_nets_mesh(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
);


BptResultCode build_block_mesh(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
);

} // namespace bpt_internal


namespace
{
// ---------------------------------------------------------
// Validation
// ---------------------------------------------------------

BptResultCode validate_volume(
    const BptVolumeResult* volume
)
{
    if (volume == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        volume->width <= 0
        || volume->depth <= 0
        || volume->height <= 0
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    const auto expected =
        static_cast<
            std::size_t
        >(
            volume->width
        )
        * static_cast<
            std::size_t
        >(
            volume->depth
        )
        * static_cast<
            std::size_t
        >(
            volume->height
        );

    if (
        expected > 0
        && volume->values == nullptr
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        volume->value_count
        != expected
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    return BPT_OK;
}


BptResultCode validate_mesh_options(
    const BptMeshOptions* options
)
{
    if (options == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        options->voxel_size
        <= 0.0f
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    switch (
        options->mode
    )
    {
        case BPT_MESH_BLOCKS:
        case BPT_MESH_SURFACE_NETS:
            return BPT_OK;

        default:
            return (
                BPT_ERROR_INVALID_ARGUMENT
            );
    }
}
} // namespace


extern "C"
{


// ---------------------------------------------------------
// Legacy entry point
// ---------------------------------------------------------

BptResultCode
bpt_build_surface_mesh(
    const BptVolumeResult* volume,
    const float voxel_size,
    const std::uint8_t center_xy_enabled,
    BptMeshResult* out_mesh
)
{
    BptMeshOptions options {};

    options.voxel_size =
        voxel_size;

    options.mode =
        BPT_MESH_BLOCKS;

    options.center_xy =
        center_xy_enabled;

    return (
        bpt_build_surface_mesh_ex(
            volume,
            &options,
            out_mesh
        )
    );
}


// ---------------------------------------------------------
// Extended entry point
// ---------------------------------------------------------

BptResultCode
bpt_build_surface_mesh_ex(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
)
{
    if (out_mesh == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    /*
     * Guarantee a safe empty output even when validation
     * fails.
     */
    *out_mesh =
        BptMeshResult {};

    const auto volume_validation =
        validate_volume(
            volume
        );

    if (
        volume_validation
        != BPT_OK
    )
    {
        return (
            volume_validation
        );
    }

    const auto options_validation =
        validate_mesh_options(
            options
        );

    if (
        options_validation
        != BPT_OK
    )
    {
        return (
            options_validation
        );
    }

    /*
     * Empty volume = valid empty mesh for every mesher.
     */
    if (
        volume->occupied_count == 0
        || volume->has_bounds == 0
    )
    {
        return BPT_OK;
    }

    try
    {
        switch (
            options->mode
        )
        {
            case BPT_MESH_BLOCKS:
                return (
                    bpt_internal::build_block_mesh(
                        volume,
                        options,
                        out_mesh
                    )
                );

            case BPT_MESH_SURFACE_NETS:
                return (
                    bpt_internal
                        ::build_surface_nets_mesh(
                            volume,
                            options,
                            out_mesh
                        )
                );

            default:
                /*
                 * validate_mesh_options already rejects
                 * this case, but keep the dispatch
                 * defensive.
                 */
                return (
                    BPT_ERROR_INVALID_ARGUMENT
                );
        }
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


} // extern "C"
