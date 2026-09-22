#pragma once

#include "test_mesh_blocks_geometry.h"

namespace
{

// ---------------------------------------------------------
// Determinism
// ---------------------------------------------------------

void test_blocks_is_deterministic()
{
    TestVolume volume(
        8,
        8,
        8
    );

    volume.fill_box(
        1,
        5,
        1,
        4,
        1,
        4
    );

    volume.set(
        6,
        3,
        2
    );

    volume.set(
        2,
        5,
        4
    );

    volume.set(
        4,
        2,
        5
    );

    auto first =
        build_extended_blocks(
            volume,
            1.0f,
            false
        );

    auto second =
        build_extended_blocks(
            volume,
            1.0f,
            false
        );

    bpt_test::assert_mesh_valid(
        first
    );

    bpt_test::assert_mesh_valid(
        second
    );

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
// Voxel size
// ---------------------------------------------------------

void test_voxel_size_scales_geometry()
{
    TestVolume volume(
        4,
        4,
        4
    );

    volume.set(
        1,
        1,
        1
    );

    auto mesh =
        build_extended_blocks(
            volume,
            0.5f,
            false
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    bpt_test::assert_near(
        bounds.min_x,
        0.5f
    );

    bpt_test::assert_near(
        bounds.max_x,
        1.0f
    );

    bpt_test::assert_near(
        bounds.min_y,
        0.5f
    );

    bpt_test::assert_near(
        bounds.max_y,
        1.0f
    );

    bpt_test::assert_near(
        bounds.min_z,
        0.5f
    );

    bpt_test::assert_near(
        bounds.max_z,
        1.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Historical XY centering
// ---------------------------------------------------------

void test_center_xy_preserves_historical_coordinates()
{
    TestVolume volume(
        4,
        6,
        5
    );

    volume.set(
        1,
        2,
        3
    );

    /*
     * voxel_size = 2
     *
     * X offset:
     * width * voxel_size / 2
     * = 4 * 2 / 2
     * = 4
     *
     * voxel X corners:
     * 1*2 - 4 = -2
     * 2*2 - 4 =  0
     *
     * Y offset:
     * 6 * 2 / 2
     * = 6
     *
     * voxel Y corners:
     * 2*2 - 6 = -2
     * 3*2 - 6 =  0
     *
     * Z is intentionally not centered.
     */
    auto mesh =
        build_extended_blocks(
            volume,
            2.0f,
            true
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    bpt_test::assert_near(
        bounds.min_x,
        -2.0f
    );

    bpt_test::assert_near(
        bounds.max_x,
        0.0f
    );

    bpt_test::assert_near(
        bounds.min_y,
        -2.0f
    );

    bpt_test::assert_near(
        bounds.max_y,
        0.0f
    );

    bpt_test::assert_near(
        bounds.min_z,
        6.0f
    );

    bpt_test::assert_near(
        bounds.max_z,
        8.0f
    );

    bpt_free_mesh(
        &mesh
    );
}

} // namespace
