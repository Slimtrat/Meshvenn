#include "bpt_core.h"
#include "test_mesh_helpers.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <map>
#include <utility>


namespace
{


using bpt_test::TestVolume;


// ---------------------------------------------------------
// Helpers
// ---------------------------------------------------------

BptMeshResult build_surface_nets(
    const TestVolume& test_volume,
    const float voxel_size = 1.0f,
    const bool center_xy = false
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


struct Vec3
{
    float x;
    float y;
    float z;
};


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


// ---------------------------------------------------------
// Outward winding for a convex isolated voxel
// ---------------------------------------------------------

void assert_single_voxel_winding_outward(
    const BptMeshResult& mesh,
    const Vec3& center
)
{
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

        assert(
            mesh.polygon_sizes[
                polygon
            ]
            == 4
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

        const auto normal =
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

        const Vec3 centroid {
            (
                a.x
                + b.x
                + c.x
                + d.x
            )
            * 0.25f,

            (
                a.y
                + b.y
                + c.y
                + d.y
            )
            * 0.25f,

            (
                a.z
                + b.z
                + c.z
                + d.z
            )
            * 0.25f,
        };

        const auto outward =
            subtract(
                centroid,
                center
            );

        assert(
            dot(
                normal,
                outward
            )
            > 0.0f
        );
    }
}


// ---------------------------------------------------------
// Single voxel
// ---------------------------------------------------------

void test_single_voxel()
{
    TestVolume volume(
        3,
        3,
        3
    );

    volume.set(
        1,
        1,
        1
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    /*
     * One occupied sample has eight surrounding
     * boundary cells.
     *
     * Surface Nets therefore creates:
     *
     * 8 representative vertices
     * 6 sign-changing sample edges -> 6 quads
     */
    assert(
        mesh.vertex_float_count
        == 8u * 3u
    );

    assert(
        mesh.polygon_count
        == 6u
    );

    assert(
        mesh.index_count
        == 24u
    );

    assert_no_degenerate_quads(
        mesh
    );

    assert_closed_two_manifold(
        mesh
    );

    /*
     * Historical voxel envelope:
     *
     * [1, 2]³
     *
     * Surface Nets may move the representative
     * vertices inside that envelope, but must never
     * escape it for this isolated binary sample.
     */
    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    assert(
        bounds.min_x >= 1.0f
    );

    assert(
        bounds.max_x <= 2.0f
    );

    assert(
        bounds.min_y >= 1.0f
    );

    assert(
        bounds.max_y <= 2.0f
    );

    assert(
        bounds.min_z >= 1.0f
    );

    assert(
        bounds.max_z <= 2.0f
    );

    assert(
        bounds.min_x
        < bounds.max_x
    );

    assert(
        bounds.min_y
        < bounds.max_y
    );

    assert(
        bounds.min_z
        < bounds.max_z
    );

    assert_single_voxel_winding_outward(
        mesh,
        Vec3 {
            1.5f,
            1.5f,
            1.5f,
        }
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Minimum grid boundary
// ---------------------------------------------------------

void test_voxel_at_minimum_boundary()
{
    TestVolume volume(
        4,
        4,
        4
    );

    volume.set(
        0,
        0,
        0
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    assert(
        mesh.vertex_float_count
        == 8u * 3u
    );

    assert(
        mesh.polygon_count
        == 6u
    );

    assert_no_degenerate_quads(
        mesh
    );

    assert_closed_two_manifold(
        mesh
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    /*
     * The virtual empty padding must close the
     * surface at x/y/z = 0 rather than dropping
     * boundary polygons.
     */
    assert(
        bounds.min_x >= 0.0f
    );

    assert(
        bounds.min_y >= 0.0f
    );

    assert(
        bounds.min_z >= 0.0f
    );

    assert(
        bounds.max_x <= 1.0f
    );

    assert(
        bounds.max_y <= 1.0f
    );

    assert(
        bounds.max_z <= 1.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Maximum grid boundary
// ---------------------------------------------------------

void test_voxel_at_maximum_boundary()
{
    TestVolume volume(
        4,
        5,
        6
    );

    volume.set(
        3,
        4,
        5
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    assert(
        mesh.vertex_float_count
        == 8u * 3u
    );

    assert(
        mesh.polygon_count
        == 6u
    );

    assert_no_degenerate_quads(
        mesh
    );

    assert_closed_two_manifold(
        mesh
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    assert(
        bounds.min_x >= 3.0f
    );

    assert(
        bounds.max_x <= 4.0f
    );

    assert(
        bounds.min_y >= 4.0f
    );

    assert(
        bounds.max_y <= 5.0f
    );

    assert(
        bounds.min_z >= 5.0f
    );

    assert(
        bounds.max_z <= 6.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Solid block
// ---------------------------------------------------------

void test_solid_block_is_closed()
{
    TestVolume volume(
        7,
        7,
        7
    );

    volume.fill_box(
        2,
        4,
        2,
        4,
        2,
        4
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    assert(
        mesh.vertex_float_count
        > 0
    );

    assert(
        mesh.polygon_count
        > 0
    );

    assert_no_degenerate_quads(
        mesh
    );

    assert_closed_two_manifold(
        mesh
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    /*
     * Occupied voxels span the historical envelope:
     *
     * [2,5] on every axis.
     */
    assert(
        bounds.min_x >= 2.0f
    );

    assert(
        bounds.max_x <= 5.0f
    );

    assert(
        bounds.min_y >= 2.0f
    );

    assert(
        bounds.max_y <= 5.0f
    );

    assert(
        bounds.min_z >= 2.0f
    );

    assert(
        bounds.max_z <= 5.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Two disconnected components
// ---------------------------------------------------------

void test_disconnected_voxels()
{
    TestVolume volume(
        7,
        7,
        7
    );

    volume.set(
        1,
        1,
        1
    );

    volume.set(
        5,
        5,
        5
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    /*
     * They are sufficiently far apart that their
     * boundary cells cannot overlap.
     */
    assert(
        mesh.vertex_float_count
        == 16u * 3u
    );

    assert(
        mesh.polygon_count
        == 12u
    );

    assert(
        mesh.index_count
        == 48u
    );

    assert_no_degenerate_quads(
        mesh
    );

    /*
     * Two disconnected closed components are still
     * globally a valid closed two-manifold.
     */
    assert_closed_two_manifold(
        mesh
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Irregular face-connected shape
// ---------------------------------------------------------

void test_irregular_shape()
{
    TestVolume volume(
        8,
        8,
        8
    );

    /*
     * Build a deliberately asymmetric staircase.
     *
     * Every added voxel remains face-connected,
     * avoiding the ambiguous corner-only topology
     * case while still exercising non-axis-flat
     * Surface Nets cells.
     */
    volume.set(
        1,
        1,
        1
    );

    volume.set(
        2,
        1,
        1
    );

    volume.set(
        2,
        2,
        1
    );

    volume.set(
        3,
        2,
        1
    );

    volume.set(
        3,
        2,
        2
    );

    volume.set(
        4,
        2,
        2
    );

    volume.set(
        4,
        3,
        2
    );

    volume.set(
        4,
        3,
        3
    );

    volume.set(
        5,
        3,
        3
    );

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    assert(
        mesh.vertex_float_count
        > 0
    );

    assert(
        mesh.polygon_count
        > 0
    );

    assert_no_degenerate_quads(
        mesh
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Hollow shape
// ---------------------------------------------------------

void test_hollow_box()
{
    TestVolume volume(
        7,
        7,
        7
    );

    /*
     * Start with a 5³ solid block.
     */
    volume.fill_box(
        1,
        5,
        1,
        5,
        1,
        5
    );

    /*
     * Remove a 3³ cavity.
     */
    for (
        std::int32_t z = 2;
        z <= 4;
        ++z
    )
    {
        for (
            std::int32_t y = 2;
            y <= 4;
            ++y
        )
        {
            for (
                std::int32_t x = 2;
                x <= 4;
                ++x
            )
            {
                volume.set(
                    x,
                    y,
                    z,
                    false
                );
            }
        }
    }

    auto mesh =
        build_surface_nets(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    assert_no_degenerate_quads(
        mesh
    );

    /*
     * Both the external shell and the internal cavity
     * must be closed.
     */
    assert_closed_two_manifold(
        mesh
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Determinism
// ---------------------------------------------------------

void test_surface_nets_is_deterministic()
{
    TestVolume volume(
        9,
        8,
        7
    );

    volume.fill_box(
        1,
        5,
        1,
        4,
        1,
        3
    );

    volume.set(
        6,
        2,
        2
    );

    volume.set(
        5,
        5,
        2
    );

    volume.set(
        3,
        4,
        4
    );

    auto first =
        build_surface_nets(
            volume,
            0.75f,
            true
        );

    auto second =
        build_surface_nets(
            volume,
            0.75f,
            true
        );

    bpt_test::assert_mesh_valid(
        first
    );

    bpt_test::assert_mesh_valid(
        second
    );

    /*
     * Exact, not approximate.
     *
     * The same binary volume must always produce the
     * exact same vertex/index ordering and coordinates.
     */
    bpt_test::assert_same_mesh(
        first,
        second
    );

    bpt_free_mesh(
        &first
    );

    bpt_free_mesh(
        &second
    );
}


// ---------------------------------------------------------
// Surface Nets is geometrically different from BLOCKS
// ---------------------------------------------------------

void test_surface_nets_differs_from_blocks()
{
    TestVolume test_volume(
        3,
        3,
        3
    );

    test_volume.set(
        1,
        1,
        1
    );

    auto volume =
        test_volume.native();

    BptMeshResult blocks {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            0,
            &blocks
        )
        == BPT_OK
    );

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS
        );

    BptMeshResult surface_nets {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &surface_nets
        )
        == BPT_OK
    );

    bpt_test::assert_mesh_valid(
        blocks
    );

    bpt_test::assert_mesh_valid(
        surface_nets
    );

    /*
     * For an isolated voxel both happen to have
     * 8 vertices / 6 quads.
     *
     * But Surface Nets must not merely return the
     * block coordinates under a different mode name.
     */
    assert(
        blocks.vertex_float_count
        == surface_nets.vertex_float_count
    );

    bool found_different_coordinate =
        false;

    for (
        std::size_t index = 0;
        index < blocks.vertex_float_count;
        ++index
    )
    {
        if (
            std::abs(
                blocks.vertices[
                    index
                ]
                -
                surface_nets.vertices[
                    index
                ]
            )
            > 1e-5f
        )
        {
            found_different_coordinate =
                true;

            break;
        }
    }

    assert(
        found_different_coordinate
    );

    bpt_free_mesh(
        &blocks
    );

    bpt_free_mesh(
        &surface_nets
    );
}


} // namespace


int main()
{
    test_single_voxel();

    test_voxel_at_minimum_boundary();

    test_voxel_at_maximum_boundary();

    test_solid_block_is_closed();

    test_disconnected_voxels();

    test_irregular_shape();

    test_hollow_box();

    test_surface_nets_is_deterministic();

    test_surface_nets_differs_from_blocks();

    std::cout
        << "Surface Nets tests passed."
        << std::endl;

    return 0;
}