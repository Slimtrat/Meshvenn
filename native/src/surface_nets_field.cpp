#include "surface_nets_internal.h"

namespace bpt_internal::surface_nets_detail
{
// ---------------------------------------------------------
// Padded binary field
// ---------------------------------------------------------
//
// The original volume stores occupied voxels.
//
// Surface Nets is easier to express as samples positioned
// at voxel centres.
//
// A one-sample empty border is added around the volume:
//
// padded sample 0
//     -> virtual empty sample at -0.5 voxel
//
// padded sample 1
//     -> original voxel 0 centre at +0.5 voxel
//
// ...
//
// padded sample width
//     -> original voxel width-1 centre
//
// padded sample width+1
//     -> virtual empty sample at width+0.5 voxel
//
// Therefore the midpoint between an occupied boundary
// sample and its virtual empty neighbour lies exactly on
// the historical voxel face.
// ---------------------------------------------------------

bool sample_occupied(
    const BptVolumeResult& volume,
    const std::int32_t px,
    const std::int32_t py,
    const std::int32_t pz
)
{
    if (
        px <= 0
        || py <= 0
        || pz <= 0
        || px > volume.width
        || py > volume.depth
        || pz > volume.height
    )
    {
        return false;
    }

    const auto x =
        static_cast<
            std::size_t
        >(
            px - 1
        );

    const auto y =
        static_cast<
            std::size_t
        >(
            py - 1
        );

    const auto z =
        static_cast<
            std::size_t
        >(
            pz - 1
        );

    const auto width =
        static_cast<
            std::size_t
        >(
            volume.width
        );

    const auto depth =
        static_cast<
            std::size_t
        >(
            volume.depth
        );

    const auto index =
        (
            z
            * depth
            + y
        )
        * width
        + x;

    return (
        volume.values[
            index
        ]
        != 0
    );
}


// ---------------------------------------------------------
// World coordinates
// ---------------------------------------------------------

Vec3 sample_world_position(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    const std::int32_t px,
    const std::int32_t py,
    const std::int32_t pz
)
{
    const float voxel_size =
        options.voxel_size;

    float offset_x =
        0.0f;

    float offset_y =
        0.0f;

    if (
        options.center_xy != 0
    )
    {
        /*
         * Exactly the same X/Y centering convention
         * as the historical block mesher.
         */
        offset_x =
            static_cast<float>(
                volume.width
            )
            * voxel_size
            * 0.5f;

        offset_y =
            static_cast<float>(
                volume.depth
            )
            * voxel_size
            * 0.5f;
    }

    return Vec3 {
        (
            static_cast<float>(
                px
            )
            - 0.5f
        )
        * voxel_size
        - offset_x,

        (
            static_cast<float>(
                py
            )
            - 0.5f
        )
        * voxel_size
        - offset_y,

        (
            static_cast<float>(
                pz
            )
            - 0.5f
        )
        * voxel_size,
    };
}



} // namespace bpt_internal::surface_nets_detail
