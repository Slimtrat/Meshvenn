#include "surface_nets_internal.h"

#include <algorithm>

namespace bpt_internal::surface_nets_detail
{
Vec3 operator+(
    const Vec3& a,
    const Vec3& b
)
{
    return Vec3 {
        a.x + b.x,
        a.y + b.y,
        a.z + b.z
    };
}


Vec3 operator*(
    const Vec3& value,
    const float factor
)
{
    return Vec3 {
        value.x * factor,
        value.y * factor,
        value.z * factor
    };
}


// ---------------------------------------------------------
// Surface Nets topology
// ---------------------------------------------------------

struct CornerOffset
{
    std::int32_t x;
    std::int32_t y;
    std::int32_t z;
};


struct EdgeCorners
{
    std::uint8_t a;
    std::uint8_t b;
};


constexpr CornerOffset kCorners[8] = {
    {0, 0, 0},
    {1, 0, 0},
    {1, 1, 0},
    {0, 1, 0},

    {0, 0, 1},
    {1, 0, 1},
    {1, 1, 1},
    {0, 1, 1},
};


constexpr EdgeCorners kEdges[12] = {
    {0, 1},
    {1, 2},
    {2, 3},
    {3, 0},

    {4, 5},
    {5, 6},
    {6, 7},
    {7, 4},

    {0, 4},
    {1, 5},
    {2, 6},
    {3, 7},
};



CellGrid create_cell_grid(
    const BptVolumeResult& volume
)
{
    CellGrid grid;

    /*
     * An occupied sample at voxel x corresponds to
     * padded sample x+1.
     *
     * The boundary cells around it therefore span
     * cell coordinates x and x+1.
     */
    grid.min_x =
        std::clamp(
            volume.min_x,
            0,
            volume.width
        );

    grid.max_x =
        std::clamp(
            volume.max_x + 1,
            0,
            volume.width
        );

    grid.min_y =
        std::clamp(
            volume.min_y,
            0,
            volume.depth
        );

    grid.max_y =
        std::clamp(
            volume.max_y + 1,
            0,
            volume.depth
        );

    grid.min_z =
        std::clamp(
            volume.min_z,
            0,
            volume.height
        );

    grid.max_z =
        std::clamp(
            volume.max_z + 1,
            0,
            volume.height
        );

    if (
        grid.min_x > grid.max_x
        || grid.min_y > grid.max_y
        || grid.min_z > grid.max_z
    )
    {
        return grid;
    }

    grid.size_x =
        static_cast<
            std::size_t
        >(
            grid.max_x
            - grid.min_x
            + 1
        );

    grid.size_y =
        static_cast<
            std::size_t
        >(
            grid.max_y
            - grid.min_y
            + 1
        );

    grid.size_z =
        static_cast<
            std::size_t
        >(
            grid.max_z
            - grid.min_z
            + 1
        );

    const auto cell_count =
        grid.size_x
        * grid.size_y
        * grid.size_z;

    grid.vertices.assign(
        cell_count,
        kInvalidVertex
    );

    return grid;
}


// ---------------------------------------------------------
// Cell vertex
// ---------------------------------------------------------

bool build_cell_vertex(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    const std::int32_t cell_x,
    const std::int32_t cell_y,
    const std::int32_t cell_z,
    Vec3* out_position
)
{
    bool occupied[8];

    std::size_t occupied_count =
        0;

    for (
        std::size_t corner = 0;
        corner < 8;
        ++corner
    )
    {
        const auto& offset =
            kCorners[
                corner
            ];

        occupied[
            corner
        ] = sample_occupied(
            volume,
            cell_x + offset.x,
            cell_y + offset.y,
            cell_z + offset.z
        );

        if (
            occupied[
                corner
            ]
        )
        {
            ++occupied_count;
        }
    }

    /*
     * No sign change:
     *
     * entirely outside
     * or entirely inside.
     */
    if (
        occupied_count == 0
        || occupied_count == 8
    )
    {
        return false;
    }

    Vec3 sum;

    std::size_t crossings =
        0;

    for (
        const auto& edge :
        kEdges
    )
    {
        if (
            occupied[
                edge.a
            ]
            ==
            occupied[
                edge.b
            ]
        )
        {
            continue;
        }

        const auto& a_offset =
            kCorners[
                edge.a
            ];

        const auto& b_offset =
            kCorners[
                edge.b
            ];

        const auto a =
            sample_world_position(
                volume,
                options,
                cell_x + a_offset.x,
                cell_y + a_offset.y,
                cell_z + a_offset.z
            );

        const auto b =
            sample_world_position(
                volume,
                options,
                cell_x + b_offset.x,
                cell_y + b_offset.y,
                cell_z + b_offset.z
            );

        /*
         * Binary scalar field:
         *
         * inside  = +1
         * outside = -1
         *
         * The zero crossing therefore lies exactly
         * at the edge midpoint.
         */
        const auto midpoint =
            (
                a
                + b
            )
            * 0.5f;

        sum += midpoint;

        ++crossings;
    }

    if (
        crossings == 0
    )
    {
        return false;
    }

    const float inverse =
        1.0f
        / static_cast<float>(
            crossings
        );

    *out_position =
        sum
        * inverse;

    return true;
}


// ---------------------------------------------------------
// Generate all active-cell vertices
// ---------------------------------------------------------

void generate_cell_vertices(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    /*
     * Boundary cells are usually proportional to surface
     * area rather than volume, but reserving against the
     * occupied count gives a useful low-cost estimate.
     */
    builder.vertices.reserve(
        volume.occupied_count
        * 6
    );

    for (
        std::int32_t z = grid.min_z;
        z <= grid.max_z;
        ++z
    )
    {
        for (
            std::int32_t y = grid.min_y;
            y <= grid.max_y;
            ++y
        )
        {
            for (
                std::int32_t x = grid.min_x;
                x <= grid.max_x;
                ++x
            )
            {
                Vec3 position;

                if (
                    !build_cell_vertex(
                        volume,
                        options,
                        x,
                        y,
                        z,
                        &position
                    )
                )
                {
                    continue;
                }

                const auto vertex =
                    builder.add_vertex(
                        position
                    );

                grid.set(
                    x,
                    y,
                    z,
                    vertex
                );
            }
        }
    }
}



} // namespace bpt_internal::surface_nets_detail
