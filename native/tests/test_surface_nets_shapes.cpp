#include "test_surface_nets_helpers.h"

#include <cassert>
#include <cstdint>

namespace bpt_surface_nets_test
{

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

} // namespace bpt_surface_nets_test
