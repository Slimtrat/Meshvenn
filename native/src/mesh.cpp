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
    float voxel_size = 1.0f;

    std::vector<float> vertices;

    std::vector<std::uint32_t> indices;

    std::vector<std::uint32_t> polygon_starts;

    std::vector<std::uint8_t> polygon_sizes;

    std::unordered_map<
        VertexKey,
        std::uint32_t,
        VertexKeyHash
    > vertex_cache;

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
            return found->second;
        }

        const auto vertex_index =
            static_cast<
                std::uint32_t
            >(
                vertices.size()
                / 3
            );

        vertices.push_back(
            static_cast<float>(x)
            * voxel_size
        );

        vertices.push_back(
            static_cast<float>(y)
            * voxel_size
        );

        vertices.push_back(
            static_cast<float>(z)
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


bool occupied(
    const BptVolumeResult& volume,
    const std::int32_t x,
    const std::int32_t y,
    const std::int32_t z
)
{
    if (
        x < 0
        || x >= volume.width
        || y < 0
        || y >= volume.depth
        || z < 0
        || z >= volume.height
    )
    {
        return false;
    }

    const auto index =
        static_cast<
            std::size_t
        >(
            z
        )
        * static_cast<
            std::size_t
        >(
            volume.depth
        )
        * static_cast<
            std::size_t
        >(
            volume.width
        )
        + static_cast<
            std::size_t
        >(
            y
        )
        * static_cast<
            std::size_t
        >(
            volume.width
        )
        + static_cast<
            std::size_t
        >(
            x
        );

    return (
        volume.values[index]
        != 0
    );
}


void center_xy(
    MeshBuilder& builder,
    const BptVolumeResult& volume
)
{
    if (
        builder.vertices.empty()
    )
    {
        return;
    }

    const float center_x =
        static_cast<float>(
            volume.width
        )
        * builder.voxel_size
        * 0.5f;

    const float center_y =
        static_cast<float>(
            volume.depth
        )
        * builder.voxel_size
        * 0.5f;

    for (
        std::size_t index = 0;
        index < builder.vertices.size();
        index += 3
    )
    {
        builder.vertices[
            index
        ] -= center_x;

        builder.vertices[
            index + 1
        ] -= center_y;
    }
}


BptResultCode validate_volume(
    const BptVolumeResult* volume
)
{
    if (
        volume == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (
        volume->width <= 0
        || volume->depth <= 0
        || volume->height <= 0
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
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
        volume->values == nullptr
        && expected > 0
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (
        volume->value_count
        != expected
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
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

    if (
        !builder.vertices.empty()
    )
    {
        out_mesh->vertices =
            new float[
                builder
                    .vertices
                    .size()
            ];

        std::copy(
            builder.vertices.begin(),
            builder.vertices.end(),
            out_mesh->vertices
        );
    }

    if (
        !builder.indices.empty()
    )
    {
        out_mesh->indices =
            new std::uint32_t[
                builder
                    .indices
                    .size()
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
            builder.polygon_starts.begin(),
            builder.polygon_starts.end(),
            out_mesh->polygon_starts
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
            builder.polygon_sizes.begin(),
            builder.polygon_sizes.end(),
            out_mesh->polygon_sizes
        );
    }
}


}


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
    if (
        out_mesh == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    *out_mesh =
        BptMeshResult {};

    const auto validation =
        validate_volume(
            volume
        );

    if (
        validation
        != BPT_OK
    )
    {
        return validation;
    }

    if (
        voxel_size <= 0.0f
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    try
    {
        MeshBuilder builder;

        builder.voxel_size =
            voxel_size;

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

        const auto plane =
            static_cast<
                std::size_t
            >(
                width
            )
            * static_cast<
                std::size_t
            >(
                depth
            );

        for (
            std::int32_t z = 0;
            z < height;
            ++z
        )
        {
            for (
                std::int32_t y = 0;
                y < depth;
                ++y
            )
            {
                for (
                    std::int32_t x = 0;
                    x < width;
                    ++x
                )
                {
                    const auto index =
                        static_cast<
                            std::size_t
                        >(
                            z
                        )
                        * plane
                        + static_cast<
                            std::size_t
                        >(
                            y
                        )
                        * static_cast<
                            std::size_t
                        >(
                            width
                        )
                        + static_cast<
                            std::size_t
                        >(
                            x
                        );

                    if (
                        volume->values[
                            index
                        ] == 0
                    )
                    {
                        continue;
                    }

                    const bool neg_x =
                        occupied(
                            *volume,
                            x - 1,
                            y,
                            z
                        );

                    const bool pos_x =
                        occupied(
                            *volume,
                            x + 1,
                            y,
                            z
                        );

                    const bool neg_y =
                        occupied(
                            *volume,
                            x,
                            y - 1,
                            z
                        );

                    const bool pos_y =
                        occupied(
                            *volume,
                            x,
                            y + 1,
                            z
                        );

                    const bool neg_z =
                        occupied(
                            *volume,
                            x,
                            y,
                            z - 1
                        );

                    const bool pos_z =
                        occupied(
                            *volume,
                            x,
                            y,
                            z + 1
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

        if (
            center_xy_enabled
            != 0
        )
        {
            center_xy(
                builder,
                *volume
            );
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

        return BPT_ERROR_ALLOCATION_FAILED;
    }
    catch (...)
    {
        bpt_free_mesh(
            out_mesh
        );

        return BPT_ERROR_INTERNAL;
    }
}


}