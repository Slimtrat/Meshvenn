#pragma once

#include "test_volume.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>


namespace bpt_test
{

// ---------------------------------------------------------
// Mesh options
// ---------------------------------------------------------

inline BptMeshOptions mesh_options(
    const BptMeshMode mode,
    const float voxel_size = 1.0f,
    const bool center_xy = false
)
{
    BptMeshOptions options {};

    options.voxel_size =
        voxel_size;

    options.mode =
        static_cast<
            std::int32_t
        >(
            mode
        );

    options.center_xy =
        center_xy
        ? 1
        : 0;

    return options;
}


// ---------------------------------------------------------
// Basic mesh validation
// ---------------------------------------------------------

inline void assert_mesh_valid(
    const BptMeshResult& mesh
)
{
    assert(
        mesh.vertex_float_count
        % 3
        == 0
    );

    const auto vertex_count =
        mesh.vertex_float_count
        / 3;

    if (
        mesh.vertex_float_count > 0
    )
    {
        assert(
            mesh.vertices
            != nullptr
        );
    }

    if (
        mesh.index_count > 0
    )
    {
        assert(
            mesh.indices
            != nullptr
        );
    }

    if (
        mesh.polygon_count > 0
    )
    {
        assert(
            mesh.polygon_starts
            != nullptr
        );

        assert(
            mesh.polygon_sizes
            != nullptr
        );
    }

    for (
        std::size_t index = 0;
        index < mesh.vertex_float_count;
        ++index
    )
    {
        assert(
            std::isfinite(
                mesh.vertices[
                    index
                ]
            )
        );
    }

    for (
        std::size_t index = 0;
        index < mesh.index_count;
        ++index
    )
    {
        assert(
            static_cast<
                std::size_t
            >(
                mesh.indices[
                    index
                ]
            )
            < vertex_count
        );
    }

    std::size_t expected_start =
        0;

    for (
        std::size_t polygon = 0;
        polygon < mesh.polygon_count;
        ++polygon
    )
    {
        const auto start =
            static_cast<
                std::size_t
            >(
                mesh.polygon_starts[
                    polygon
                ]
            );

        const auto size =
            static_cast<
                std::size_t
            >(
                mesh.polygon_sizes[
                    polygon
                ]
            );

        assert(
            start
            == expected_start
        );

        assert(
            size >= 3
        );

        assert(
            start + size
            <= mesh.index_count
        );

        /*
         * A polygon must not contain the same vertex twice.
         */
        for (
            std::size_t a = 0;
            a < size;
            ++a
        )
        {
            for (
                std::size_t b = a + 1;
                b < size;
                ++b
            )
            {
                assert(
                    mesh.indices[
                        start + a
                    ]
                    !=
                    mesh.indices[
                        start + b
                    ]
                );
            }
        }

        expected_start +=
            size;
    }

    assert(
        expected_start
        == mesh.index_count
    );
}


// ---------------------------------------------------------
// Exact mesh comparison
// ---------------------------------------------------------

inline void assert_same_mesh(
    const BptMeshResult& a,
    const BptMeshResult& b
)
{
    assert(
        a.vertex_float_count
        == b.vertex_float_count
    );

    assert(
        a.index_count
        == b.index_count
    );

    assert(
        a.polygon_count
        == b.polygon_count
    );

    for (
        std::size_t index = 0;
        index < a.vertex_float_count;
        ++index
    )
    {
        assert(
            a.vertices[
                index
            ]
            ==
            b.vertices[
                index
            ]
        );
    }

    for (
        std::size_t index = 0;
        index < a.index_count;
        ++index
    )
    {
        assert(
            a.indices[
                index
            ]
            ==
            b.indices[
                index
            ]
        );
    }

    for (
        std::size_t polygon = 0;
        polygon < a.polygon_count;
        ++polygon
    )
    {
        assert(
            a.polygon_starts[
                polygon
            ]
            ==
            b.polygon_starts[
                polygon
            ]
        );

        assert(
            a.polygon_sizes[
                polygon
            ]
            ==
            b.polygon_sizes[
                polygon
            ]
        );
    }
}


// ---------------------------------------------------------
// Vertex bounds
// ---------------------------------------------------------

struct MeshBounds
{
    float min_x = 0.0f;
    float max_x = 0.0f;

    float min_y = 0.0f;
    float max_y = 0.0f;

    float min_z = 0.0f;
    float max_z = 0.0f;
};


inline MeshBounds mesh_bounds(
    const BptMeshResult& mesh
)
{
    assert(
        mesh.vertex_float_count
        >= 3
    );

    MeshBounds result;

    result.min_x =
        result.max_x =
            mesh.vertices[0];

    result.min_y =
        result.max_y =
            mesh.vertices[1];

    result.min_z =
        result.max_z =
            mesh.vertices[2];

    for (
        std::size_t index = 3;
        index < mesh.vertex_float_count;
        index += 3
    )
    {
        const float x =
            mesh.vertices[
                index
            ];

        const float y =
            mesh.vertices[
                index + 1
            ];

        const float z =
            mesh.vertices[
                index + 2
            ];

        result.min_x =
            std::min(
                result.min_x,
                x
            );

        result.max_x =
            std::max(
                result.max_x,
                x
            );

        result.min_y =
            std::min(
                result.min_y,
                y
            );

        result.max_y =
            std::max(
                result.max_y,
                y
            );

        result.min_z =
            std::min(
                result.min_z,
                z
            );

        result.max_z =
            std::max(
                result.max_z,
                z
            );
    }

    return result;
}


// ---------------------------------------------------------
// Floating-point helper
// ---------------------------------------------------------

inline void assert_near(
    const float actual,
    const float expected,
    const float epsilon = 1e-5f
)
{
    assert(
        std::abs(
            actual
            - expected
        )
        <= epsilon
    );
}


} // namespace bpt_test