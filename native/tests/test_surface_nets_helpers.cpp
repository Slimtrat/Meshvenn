#include "test_surface_nets_helpers.h"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <utility>

namespace bpt_surface_nets_test
{

BptMeshResult build_surface_nets(
    const TestVolume& test_volume,
    const float voxel_size,
    const bool center_xy
)
{
    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS,
            voxel_size,
            center_xy
        );

    BptMeshResult mesh {};

    const auto result =
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        );

    assert(
        result
        == BPT_OK
    );

    return mesh;
}


void assert_all_quads(
    const BptMeshResult& mesh
)
{
    for (
        std::size_t polygon = 0;
        polygon < mesh.polygon_count;
        ++polygon
    )
    {
        assert(
            mesh.polygon_sizes[
                polygon
            ]
            == 4
        );
    }
}




Vec3 vertex(
    const BptMeshResult& mesh,
    const std::uint32_t index
)
{
    const auto offset =
        static_cast<
            std::size_t
        >(
            index
        )
        * 3;

    assert(
        offset + 2
        < mesh.vertex_float_count
    );

    return Vec3 {
        mesh.vertices[
            offset
        ],
        mesh.vertices[
            offset + 1
        ],
        mesh.vertices[
            offset + 2
        ],
    };
}


Vec3 subtract(
    const Vec3& a,
    const Vec3& b
)
{
    return Vec3 {
        a.x - b.x,
        a.y - b.y,
        a.z - b.z,
    };
}


Vec3 cross(
    const Vec3& a,
    const Vec3& b
)
{
    return Vec3 {
        a.y * b.z
            - a.z * b.y,

        a.z * b.x
            - a.x * b.z,

        a.x * b.y
            - a.y * b.x,
    };
}


float dot(
    const Vec3& a,
    const Vec3& b
)
{
    return (
        a.x * b.x
        + a.y * b.y
        + a.z * b.z
    );
}


float length_squared(
    const Vec3& value
)
{
    return dot(
        value,
        value
    );
}


void assert_no_degenerate_quads(
    const BptMeshResult& mesh
)
{
    constexpr float epsilon =
        1e-12f;

    for (
        std::size_t polygon = 0;
        polygon < mesh.polygon_count;
        ++polygon
    )
    {
        assert(
            mesh.polygon_sizes[
                polygon
            ]
            == 4
        );

        const auto start =
            static_cast<
                std::size_t
            >(
                mesh.polygon_starts[
                    polygon
                ]
            );

        const auto a =
            vertex(
                mesh,
                mesh.indices[
                    start
                ]
            );

        const auto b =
            vertex(
                mesh,
                mesh.indices[
                    start + 1
                ]
            );

        const auto c =
            vertex(
                mesh,
                mesh.indices[
                    start + 2
                ]
            );

        const auto d =
            vertex(
                mesh,
                mesh.indices[
                    start + 3
                ]
            );

        /*
         * A non-planar quad is valid.
         *
         * Check both triangles rather than requiring
         * all four points to share one plane.
         */
        const auto normal_abc =
            cross(
                subtract(
                    b,
                    a
                ),
                subtract(
                    c,
                    a
                )
            );

        const auto normal_acd =
            cross(
                subtract(
                    c,
                    a
                ),
                subtract(
                    d,
                    a
                )
            );

        assert(
            (
                length_squared(
                    normal_abc
                )
                > epsilon
            )
            ||
            (
                length_squared(
                    normal_acd
                )
                > epsilon
            )
        );
    }
}


// ---------------------------------------------------------
// Closed-manifold edge check
// ---------------------------------------------------------

using Edge = std::pair<
    std::uint32_t,
    std::uint32_t
>;


Edge canonical_edge(
    const std::uint32_t a,
    const std::uint32_t b
)
{
    if (a < b)
    {
        return {
            a,
            b
        };
    }

    return {
        b,
        a
    };
}


void assert_closed_two_manifold(
    const BptMeshResult& mesh
)
{
    std::map<
        Edge,
        std::size_t
    >
        edge_counts;

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

        for (
            std::size_t corner = 0;
            corner < size;
            ++corner
        )
        {
            const auto next =
                (
                    corner + 1
                )
                % size;

            const auto a =
                mesh.indices[
                    start + corner
                ];

            const auto b =
                mesh.indices[
                    start + next
                ];

            ++edge_counts[
                canonical_edge(
                    a,
                    b
                )
            ];
        }
    }

    assert(
        !edge_counts.empty()
    );

    for (
        const auto& [
            edge,
            count
        ] :
        edge_counts
    )
    {
        (void) edge;

        /*
         * Closed orientable 2-manifold:
         *
         * every mesh edge is shared by exactly
         * two polygons.
         */
        assert(
            count
            == 2
        );
    }
}

} // namespace bpt_surface_nets_test
