#include "test_surface_nets_helpers.h"

#include <cassert>
#include <cstddef>

namespace bpt_surface_nets_test
{

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

} // namespace bpt_surface_nets_test
