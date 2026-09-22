#pragma once

#include "bpt_core.h"

#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace bpt_internal::surface_nets_detail
{
struct Vec3
{
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3& operator+=(
        const Vec3& other
    )
    {
        x += other.x;
        y += other.y;
        z += other.z;

        return *this;
    }
};
Vec3 operator+(const Vec3& a, const Vec3& b);
Vec3 operator*(const Vec3& value, float factor);

constexpr std::uint32_t kInvalidVertex =
    std::numeric_limits<std::uint32_t>::max();
struct SurfaceNetsBuilder
{
    std::vector<float>
        vertices;

    std::vector<std::uint32_t>
        indices;

    std::vector<std::uint32_t>
        polygon_starts;

    std::vector<std::uint8_t>
        polygon_sizes;


    std::uint32_t add_vertex(
        const Vec3& point
    )
    {
        const auto index =
            static_cast<
                std::uint32_t
            >(
                vertices.size()
                / 3
            );

        vertices.push_back(
            point.x
        );

        vertices.push_back(
            point.y
        );

        vertices.push_back(
            point.z
        );

        return index;
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

struct CellGrid
{
    std::int32_t min_x = 0;
    std::int32_t min_y = 0;
    std::int32_t min_z = 0;

    std::int32_t max_x = -1;
    std::int32_t max_y = -1;
    std::int32_t max_z = -1;

    std::size_t size_x = 0;
    std::size_t size_y = 0;
    std::size_t size_z = 0;

    std::vector<std::uint32_t>
        vertices;


    bool contains(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        return (
            x >= min_x
            && x <= max_x
            && y >= min_y
            && y <= max_y
            && z >= min_z
            && z <= max_z
        );
    }


    std::size_t index(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        const auto local_x =
            static_cast<
                std::size_t
            >(
                x - min_x
            );

        const auto local_y =
            static_cast<
                std::size_t
            >(
                y - min_y
            );

        const auto local_z =
            static_cast<
                std::size_t
            >(
                z - min_z
            );

        return (
            (
                local_z
                * size_y
                + local_y
            )
            * size_x
            + local_x
        );
    }


    std::uint32_t get(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        if (
            !contains(
                x,
                y,
                z
            )
        )
        {
            return (
                kInvalidVertex
            );
        }

        return vertices[
            index(
                x,
                y,
                z
            )
        ];
    }


    void set(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z,
        const std::uint32_t vertex
    )
    {
        vertices[
            index(
                x,
                y,
                z
            )
        ] = vertex;
    }
};

bool sample_occupied(
    const BptVolumeResult& volume,
    std::int32_t px,
    std::int32_t py,
    std::int32_t pz
);

Vec3 sample_world_position(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    std::int32_t px,
    std::int32_t py,
    std::int32_t pz
);

CellGrid create_cell_grid(const BptVolumeResult& volume);

bool build_cell_vertex(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    std::int32_t cell_x,
    std::int32_t cell_y,
    std::int32_t cell_z,
    Vec3* out_position
);

void generate_cell_vertices(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    CellGrid& grid,
    SurfaceNetsBuilder& builder
);

BptResultCode generate_x_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
);

BptResultCode generate_y_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
);

BptResultCode generate_z_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
);

void copy_to_result(
    SurfaceNetsBuilder& builder,
    BptMeshResult* out_mesh
);

} // namespace bpt_internal::surface_nets_detail