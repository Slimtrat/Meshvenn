#pragma once

#include "bpt_core.h"

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
// Test volume
// ---------------------------------------------------------

class TestVolume
{
public:
    TestVolume(
        const std::int32_t width,
        const std::int32_t depth,
        const std::int32_t height
    )
        : width_(width),
          depth_(depth),
          height_(height),
          values_(
              static_cast<std::size_t>(width)
              * static_cast<std::size_t>(depth)
              * static_cast<std::size_t>(height),
              0
          )
    {
        assert(
            width > 0
        );

        assert(
            depth > 0
        );

        assert(
            height > 0
        );
    }


    std::int32_t width() const
    {
        return width_;
    }


    std::int32_t depth() const
    {
        return depth_;
    }


    std::int32_t height() const
    {
        return height_;
    }


    std::size_t index(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        assert(
            x >= 0
            && x < width_
        );

        assert(
            y >= 0
            && y < depth_
        );

        assert(
            z >= 0
            && z < height_
        );

        return (
            (
                static_cast<std::size_t>(
                    z
                )
                * static_cast<std::size_t>(
                    depth_
                )
                + static_cast<std::size_t>(
                    y
                )
            )
            * static_cast<std::size_t>(
                width_
            )
            + static_cast<std::size_t>(
                x
            )
        );
    }


    bool occupied(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        return (
            values_[
                index(
                    x,
                    y,
                    z
                )
            ]
            != 0
        );
    }


    void set(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z,
        const bool occupied = true
    )
    {
        values_[
            index(
                x,
                y,
                z
            )
        ] = (
            occupied
            ? 1
            : 0
        );
    }


    void fill_box(
        const std::int32_t min_x,
        const std::int32_t max_x,
        const std::int32_t min_y,
        const std::int32_t max_y,
        const std::int32_t min_z,
        const std::int32_t max_z
    )
    {
        assert(
            min_x <= max_x
        );

        assert(
            min_y <= max_y
        );

        assert(
            min_z <= max_z
        );

        for (
            std::int32_t z = min_z;
            z <= max_z;
            ++z
        )
        {
            for (
                std::int32_t y = min_y;
                y <= max_y;
                ++y
            )
            {
                for (
                    std::int32_t x = min_x;
                    x <= max_x;
                    ++x
                )
                {
                    set(
                        x,
                        y,
                        z
                    );
                }
            }
        }
    }


    std::size_t occupied_count() const
    {
        return static_cast<
            std::size_t
        >(
            std::count_if(
                values_.begin(),
                values_.end(),
                [](
                    const std::uint8_t value
                )
                {
                    return (
                        value != 0
                    );
                }
            )
        );
    }


    BptVolumeResult native() const
    {
        BptVolumeResult result {};

        result.width =
            width_;

        result.depth =
            depth_;

        result.height =
            height_;

        /*
         * The native API does not mutate the input volume.
         *
         * Its historical C ABI unfortunately does not mark
         * this pointer const, so expose the test buffer here.
         */
        result.values =
            const_cast<
                std::uint8_t*
            >(
                values_.data()
            );

        result.value_count =
            values_.size();

        result.occupied_count =
            occupied_count();

        if (
            result.occupied_count
            == 0
        )
        {
            result.has_bounds =
                0;

            return result;
        }

        std::int32_t min_x =
            std::numeric_limits<
                std::int32_t
            >::max();

        std::int32_t min_y =
            min_x;

        std::int32_t min_z =
            min_x;

        std::int32_t max_x =
            std::numeric_limits<
                std::int32_t
            >::min();

        std::int32_t max_y =
            max_x;

        std::int32_t max_z =
            max_x;

        for (
            std::int32_t z = 0;
            z < height_;
            ++z
        )
        {
            for (
                std::int32_t y = 0;
                y < depth_;
                ++y
            )
            {
                for (
                    std::int32_t x = 0;
                    x < width_;
                    ++x
                )
                {
                    if (
                        !occupied(
                            x,
                            y,
                            z
                        )
                    )
                    {
                        continue;
                    }

                    min_x =
                        std::min(
                            min_x,
                            x
                        );

                    max_x =
                        std::max(
                            max_x,
                            x
                        );

                    min_y =
                        std::min(
                            min_y,
                            y
                        );

                    max_y =
                        std::max(
                            max_y,
                            y
                        );

                    min_z =
                        std::min(
                            min_z,
                            z
                        );

                    max_z =
                        std::max(
                            max_z,
                            z
                        );
                }
            }
        }

        result.has_bounds =
            1;

        result.min_x =
            min_x;

        result.max_x =
            max_x;

        result.min_y =
            min_y;

        result.max_y =
            max_y;

        result.min_z =
            min_z;

        result.max_z =
            max_z;

        return result;
    }


private:
    std::int32_t width_;
    std::int32_t depth_;
    std::int32_t height_;

    std::vector<
        std::uint8_t
    >
        values_;
};


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