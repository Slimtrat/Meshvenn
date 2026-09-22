#include "surface_nets_internal.h"

namespace bpt_internal::surface_nets_detail
{
// ---------------------------------------------------------
// Quad helper
// ---------------------------------------------------------

bool valid_quad(
    const std::uint32_t a,
    const std::uint32_t b,
    const std::uint32_t c,
    const std::uint32_t d
)
{
    return (
        a != kInvalidVertex
        && b != kInvalidVertex
        && c != kInvalidVertex
        && d != kInvalidVertex
    );
}


void add_oriented_quad(
    SurfaceNetsBuilder& builder,
    const bool low_sample_inside,
    const std::uint32_t a,
    const std::uint32_t b,
    const std::uint32_t c,
    const std::uint32_t d
)
{
    if (
        low_sample_inside
    )
    {
        /*
         * Occupied -> empty while moving in the positive
         * axis direction.
         *
         * Outward normal therefore points +axis.
         */
        builder.add_quad(
            a,
            b,
            c,
            d
        );
    }
    else
    {
        /*
         * Empty -> occupied.
         *
         * Outward normal points -axis.
         */
        builder.add_quad(
            d,
            c,
            b,
            a
        );
    }
}


// ---------------------------------------------------------
// X-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_x_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y + 1;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z + 1;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px + 1,
                        py,
                        pz
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * Viewed from +X:
                 *
                 * a ---- b
                 * |      |
                 * d ---- c
                 *
                 * gives +X winding.
                 */
                const auto a =
                    grid.get(
                        px,
                        py - 1,
                        pz - 1
                    );

                const auto b =
                    grid.get(
                        px,
                        py,
                        pz - 1
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px,
                        py - 1,
                        pz
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}


// ---------------------------------------------------------
// Y-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_y_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x + 1;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z + 1;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px,
                        py + 1,
                        pz
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * +Y winding:
                 *
                 * lower X/lower Z
                 * -> lower X/upper Z
                 * -> upper X/upper Z
                 * -> upper X/lower Z
                 */
                const auto a =
                    grid.get(
                        px - 1,
                        py,
                        pz - 1
                    );

                const auto b =
                    grid.get(
                        px - 1,
                        py,
                        pz
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px,
                        py,
                        pz - 1
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}


// ---------------------------------------------------------
// Z-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_z_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x + 1;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y + 1;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz + 1
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * +Z winding:
                 *
                 * lower X/lower Y
                 * -> upper X/lower Y
                 * -> upper X/upper Y
                 * -> lower X/upper Y
                 */
                const auto a =
                    grid.get(
                        px - 1,
                        py - 1,
                        pz
                    );

                const auto b =
                    grid.get(
                        px,
                        py - 1,
                        pz
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px - 1,
                        py,
                        pz
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}



} // namespace bpt_internal::surface_nets_detail
