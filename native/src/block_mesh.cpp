#include "block_mesh_builder.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace bpt_internal
{

// ---------------------------------------------------------
// Legacy block mesher
// ---------------------------------------------------------

BptResultCode build_block_mesh(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
)
{
    MeshBuilder builder;

    builder.voxel_size =
        options->voxel_size;

    if (
        options->center_xy != 0
    )
    {
        /*
         * Historical world-space centering.
         *
         * Keep this exactly aligned with the previous
         * bpt_build_surface_mesh implementation.
         */
        builder.offset_x =
            static_cast<float>(
                volume->width
            )
            * options->voxel_size
            * 0.5f;

        builder.offset_y =
            static_cast<float>(
                volume->depth
            )
            * options->voxel_size
            * 0.5f;
    }

    const auto occupied_count =
        volume->occupied_count;

    /*
     * Keep historical reserve heuristics.
     */
    builder.vertex_cache.reserve(
        occupied_count
        * 2
    );

    builder.vertices.reserve(
        occupied_count
        * 3
    );

    builder.indices.reserve(
        occupied_count
        * 12
    );

    builder.polygon_starts.reserve(
        occupied_count
        * 3
    );

    builder.polygon_sizes.reserve(
        occupied_count
        * 3
    );

    const auto width =
        volume->width;

    const auto depth =
        volume->depth;

    const auto height =
        volume->height;

    const auto width_size =
        static_cast<
            std::size_t
        >(
            width
        );

    const auto depth_size =
        static_cast<
            std::size_t
        >(
            depth
        );

    const auto plane =
        width_size
        * depth_size;

    const auto* values =
        volume->values;

    /*
     * Clamp bounds defensively.
     */
    const auto min_x =
        std::clamp(
            volume->min_x,
            0,
            width - 1
        );

    const auto max_x =
        std::clamp(
            volume->max_x,
            0,
            width - 1
        );

    const auto min_y =
        std::clamp(
            volume->min_y,
            0,
            depth - 1
        );

    const auto max_y =
        std::clamp(
            volume->max_y,
            0,
            depth - 1
        );

    const auto min_z =
        std::clamp(
            volume->min_z,
            0,
            height - 1
        );

    const auto max_z =
        std::clamp(
            volume->max_z,
            0,
            height - 1
        );

    if (
        min_x > max_x
        || min_y > max_y
        || min_z > max_z
    )
    {
        return BPT_OK;
    }

    for (
        std::int32_t z = min_z;
        z <= max_z;
        ++z
    )
    {
        const auto z_offset =
            static_cast<
                std::size_t
            >(
                z
            )
            * plane;

        for (
            std::int32_t y = min_y;
            y <= max_y;
            ++y
        )
        {
            const auto row_offset =
                z_offset
                + static_cast<
                    std::size_t
                >(
                    y
                )
                * width_size;

            for (
                std::int32_t x = min_x;
                x <= max_x;
                ++x
            )
            {
                const auto index =
                    row_offset
                    + static_cast<
                        std::size_t
                    >(
                        x
                    );

                if (
                    values[index]
                    == 0
                )
                {
                    continue;
                }

                /*
                 * Direct neighbour accesses.
                 *
                 * This is the historical block-mesh
                 * algorithm and deliberately stays
                 * unchanged.
                 */
                const bool neg_x =
                    (
                        x > 0
                        && values[
                            index - 1
                        ] != 0
                    );

                const bool pos_x =
                    (
                        x + 1 < width
                        && values[
                            index + 1
                        ] != 0
                    );

                const bool neg_y =
                    (
                        y > 0
                        && values[
                            index
                            - width_size
                        ] != 0
                    );

                const bool pos_y =
                    (
                        y + 1 < depth
                        && values[
                            index
                            + width_size
                        ] != 0
                    );

                const bool neg_z =
                    (
                        z > 0
                        && values[
                            index
                            - plane
                        ] != 0
                    );

                const bool pos_z =
                    (
                        z + 1 < height
                        && values[
                            index
                            + plane
                        ] != 0
                    );

                if (!neg_x)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x,
                            y,
                            z
                        ),
                        builder.get_vertex(
                            x,
                            y,
                            z + 1
                        ),
                        builder.get_vertex(
                            x,
                            y + 1,
                            z + 1
                        ),
                        builder.get_vertex(
                            x,
                            y + 1,
                            z
                        )
                    );
                }

                if (!pos_x)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x + 1,
                            y,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z + 1
                        ),
                        builder.get_vertex(
                            x + 1,
                            y,
                            z + 1
                        )
                    );
                }

                if (!neg_y)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x,
                            y,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y,
                            z + 1
                        ),
                        builder.get_vertex(
                            x,
                            y,
                            z + 1
                        )
                    );
                }

                if (!pos_y)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x,
                            y + 1,
                            z
                        ),
                        builder.get_vertex(
                            x,
                            y + 1,
                            z + 1
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z + 1
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z
                        )
                    );
                }

                if (!neg_z)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x,
                            y,
                            z
                        ),
                        builder.get_vertex(
                            x,
                            y + 1,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z
                        ),
                        builder.get_vertex(
                            x + 1,
                            y,
                            z
                        )
                    );
                }

                if (!pos_z)
                {
                    builder.add_quad(
                        builder.get_vertex(
                            x,
                            y,
                            z + 1
                        ),
                        builder.get_vertex(
                            x + 1,
                            y,
                            z + 1
                        ),
                        builder.get_vertex(
                            x + 1,
                            y + 1,
                            z + 1
                        ),
                        builder.get_vertex(
                            x,
                            y + 1,
                            z + 1
                        )
                    );
                }
            }
        }
    }

    copy_to_result(
        builder,
        out_mesh
    );

    return BPT_OK;
}

} // namespace bpt_internal
