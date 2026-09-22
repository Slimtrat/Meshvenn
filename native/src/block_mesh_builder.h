#pragma once

#include "bpt_core.h"

#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace bpt_internal
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


// ---------------------------------------------------------
// Legacy block mesh builder
// ---------------------------------------------------------

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

void copy_to_result(
    MeshBuilder& builder,
    BptMeshResult* out_mesh
);

} // namespace bpt_internal
