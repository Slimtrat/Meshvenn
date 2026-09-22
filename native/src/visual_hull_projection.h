#pragma once

#include "visual_hull_internal.h"

#include <algorithm>

namespace bpt_visual_hull_detail
{

inline bool sample_projection(
    const CompiledProjection& projection,
    const float nx,
    const float ny,
    const float nz
)
{
    const float x1 =
        nx * projection.cos_az
        - ny * projection.sin_az;

    const float y1 =
        nx * projection.sin_az
        + ny * projection.cos_az;

    const float z2 =
        y1 * projection.sin_el
        + nz * projection.cos_el;

    float u =
        (
            (
                x1
                / projection.horizontal_extent
            )
            + 1.0f
        )
        * 0.5f;

    const float v =
        (
            (
                z2
                / projection.vertical_extent
            )
            + 1.0f
        )
        * 0.5f;

    if (projection.flip_x)
    {
        u =
            1.0f
            - u;
    }

    if (
        u < 0.0f
        || u > 1.0f
        || v < 0.0f
        || v > 1.0f
    )
    {
        return false;
    }

    const auto x =
        std::clamp(
            static_cast<
                std::int32_t
            >(
                u
                * projection.width_minus_one
                + 0.5f
            ),
            0,
            projection.width - 1
        );

    const auto y =
        std::clamp(
            static_cast<
                std::int32_t
            >(
                v
                * projection.height_minus_one
                + 0.5f
            ),
            0,
            projection.height - 1
        );

    const auto index =
        static_cast<
            std::size_t
        >(
            y
        )
        * static_cast<
            std::size_t
        >(
            projection.width
        )
        + static_cast<
            std::size_t
        >(
            x
        );

    return (
        projection.mask[index]
        != 0
    );
}


inline bool survives_projection(
    const CompiledProjection& projection,
    const float nx,
    const float ny,
    const float nz,
    const bool symmetry_x
)
{
    if (
        !sample_projection(
            projection,
            nx,
            ny,
            nz
        )
    )
    {
        return false;
    }

    if (!symmetry_x)
    {
        return true;
    }

    /*
     * Conservative X symmetry:
     *
     * a voxel survives only when both it and
     * its mirrored X position satisfy the
     * silhouette.
     *
     * Therefore x and -x always receive the
     * same result and the volume stays
     * symmetrical without creating geometry
     * outside the source silhouettes.
     */
    return sample_projection(
        projection,
        -nx,
        ny,
        nz
    );
}

} // namespace bpt_visual_hull_detail
