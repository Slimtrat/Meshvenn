#include "bpt_core.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <new>
#include <unordered_map>
#include <utility>
#include <vector>


namespace
{


struct VertexKey
{
    std::int32_t x;
    std::int32_t y;
    std::int32_t z;

    bool operator==(
        const VertexKey& other
    ) const noexcept
    {
        return (
            x == other.x
            && y == other.y
            && z == other.z
        );
    }
};


struct VertexKeyHash
{
    std::size_t operator()(
        const VertexKey& key
    ) const noexcept
    {
        const auto hx =
            static_cast<std::size_t>(
                static_cast<std::uint32_t>(
                    key.x
                )
            );

        const auto hy =
            static_cast<std::size_t>(
                static_cast<std::uint32_t>(
                    key.y
                )
            );

        const auto hz =
            static_cast<std::size_t>(
                static_cast<std::uint32_t>(
                    key.z
                )
            );

        std::size_t result =
            hx * 73856093u;

        result ^=
            hy * 19349663u;

        result ^=
            hz * 83492791u;

        return result;
    }
};


struct MeshBuilder
{
    float voxel_size =
        1.0f;

    float offset_x =
        0.0f;

    float offset_y =
        0.0f;

    std::vector<float>
        vertices;

    std::vector<std::uint32_t>
        indices;

    std::vector<std::uint32_t>
        polygon_starts;

    std::vector<std::uint8_t>
        polygon_sizes;

    std::unordered_map<
        VertexKey,
        std::uint32_t,
        VertexKeyHash
    >
        vertex_cache;


    std::uint32_t get_vertex(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    )
    {
        const VertexKey key {
            x,
            y,
            z
        };

        const auto found =
            vertex_cache.find(
                key
            );

        if (
            found
            != vertex_cache.end()
        )
        {
            return (
                found->second
            );
        }

        const auto vertex_index =
            static_cast<
                std::uint32_t
            >(
                vertices.size()
                / 3
            );

        vertices.push_back(
            static_cast<float>(
                x
            )
            * voxel_size
            - offset_x
        );

        vertices.push_back(
            static_cast<float>(
                y
            )
            * voxel_size
            - offset_y
        );

        vertices.push_back(
            static_cast<float>(
                z
            )
            * voxel_size
        );

        vertex_cache.emplace(
            key,
            vertex_index
        );

        return vertex_index;
    }


    void add_quad(
        const std::uint32_t a,
        const std::uint32_t b,
        const std::uint32_t c,
        const std::uint32_t d
    )
    {
        polygon_starts.push_back(
            static_cast<
                std::uint32_t
            >(
                indices.size()
            )
        );

        polygon_sizes.push_back(
            4
        );

        indices.push_back(a);
        indices.push_back(b);
        indices.push_back(c);
        indices.push_back(d);
    }
};


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


void copy_to_result(
    MeshBuilder& builder,
    BptMeshResult* out_mesh
)
{
    *out_mesh =
        BptMeshResult {};

    out_mesh->vertex_float_count =
        builder.vertices.size();

    out_mesh->index_count =
        builder.indices.size();

    out_mesh->polygon_count =
        builder.polygon_sizes.size();

    if (!builder.vertices.empty())
    {
        out_mesh->vertices =
            new float[
                builder.vertices.size()
            ];

        std::copy(
            builder.vertices.begin(),
            builder.vertices.end(),
            out_mesh->vertices
        );
    }

    if (!builder.indices.empty())
    {
        out_mesh->indices =
            new std::uint32_t[
                builder.indices.size()
            ];

        std::copy(
            builder.indices.begin(),
            builder.indices.end(),
            out_mesh->indices
        );
    }

    if (
        !builder
            .polygon_starts
            .empty()
    )
    {
        out_mesh->polygon_starts =
            new std::uint32_t[
                builder
                    .polygon_starts
                    .size()
            ];

        std::copy(
            builder
                .polygon_starts
                .begin(),
            builder
                .polygon_starts
                .end(),
            out_mesh
                ->polygon_starts
        );
    }

    if (
        !builder
            .polygon_sizes
            .empty()
    )
    {
        out_mesh->polygon_sizes =
            new std::uint8_t[
                builder
                    .polygon_sizes
                    .size()
            ];

        std::copy(
            builder
                .polygon_sizes
                .begin(),
            builder
                .polygon_sizes
                .end(),
            out_mesh
                ->polygon_sizes
        );
    }
}


} // namespace


extern "C"
{


BptResultCode
bpt_build_surface_mesh(
    const BptVolumeResult* volume,
    const float voxel_size,
    const std::uint8_t center_xy_enabled,
    BptMeshResult* out_mesh
)
{
    if (out_mesh == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    *out_mesh =
        BptMeshResult {};

    const auto validation =
        validate_volume(
            volume
        );

    if (validation != BPT_OK)
    {
        return validation;
    }

    if (voxel_size <= 0.0f)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    /*
     * Empty volume = valid empty mesh.
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
        MeshBuilder builder;

        builder.voxel_size =
            voxel_size;

        if (center_xy_enabled != 0)
        {
            /*
             * Same world-space centering as
             * before, but applied while vertices
             * are emitted instead of doing a
             * second pass over the vertex buffer.
             */
            builder.offset_x =
                static_cast<float>(
                    volume->width
                )
                * voxel_size
                * 0.5f;

            builder.offset_y =
                static_cast<float>(
                    volume->depth
                )
                * voxel_size
                * 0.5f;
        }

        const auto occupied_count =
            volume->occupied_count;

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
                     * We avoid six calls to a helper
                     * that recalculated the complete
                     * 3D index every time.
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