#include "bpt_core.h"
#include "test_mesh_helpers.h"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>


namespace
{


using bpt_test::TestVolume;


// ---------------------------------------------------------
// Helpers
// ---------------------------------------------------------

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


BptMeshResult build_legacy(
    const TestVolume& test_volume,
    const float voxel_size = 1.0f,
    const bool center_xy = false
)
{
    auto volume =
        test_volume.native();

    BptMeshResult mesh {};

    const auto result =
        bpt_build_surface_mesh(
            &volume,
            voxel_size,
            center_xy
                ? 1
                : 0,
            &mesh
        );

    assert(
        result
        == BPT_OK
    );

    return mesh;
}


BptMeshResult build_extended_blocks(
    const TestVolume& test_volume,
    const float voxel_size = 1.0f,
    const bool center_xy = false
)
{
    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS,
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


// ---------------------------------------------------------
// Single voxel
// ---------------------------------------------------------

void test_single_voxel_geometry()
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
        build_legacy(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    /*
     * One isolated voxel:
     *
     * 8 unique cube corners
     * 6 exposed faces
     * 4 indices per face
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
        == 6u * 4u
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    bpt_test::assert_near(
        bounds.min_x,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_x,
        2.0f
    );

    bpt_test::assert_near(
        bounds.min_y,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_y,
        2.0f
    );

    bpt_test::assert_near(
        bounds.min_z,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_z,
        2.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Adjacent voxels
// ---------------------------------------------------------

void test_adjacent_voxels_remove_internal_face()
{
    TestVolume volume(
        4,
        3,
        3
    );

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

    auto mesh =
        build_legacy(
            volume
        );

    bpt_test::assert_mesh_valid(
        mesh
    );

    assert_all_quads(
        mesh
    );

    /*
     * Two isolated cubes would have:
     *
     * 12 faces.
     *
     * Their shared X face must disappear from both
     * voxels:
     *
     * 12 - 2 = 10 emitted quads.
     */
    assert(
        mesh.polygon_count
        == 10u
    );

    assert(
        mesh.index_count
        == 40u
    );

    /*
     * The shared vertex cache still represents the full
     * 2x1x1 cuboid lattice:
     *
     * 3 X planes
     * 2 Y planes
     * 2 Z planes
     *
     * = 12 vertices.
     */
    assert(
        mesh.vertex_float_count
        == 12u * 3u
    );

    const auto bounds =
        bpt_test::mesh_bounds(
            mesh
        );

    bpt_test::assert_near(
        bounds.min_x,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_x,
        3.0f
    );

    bpt_test::assert_near(
        bounds.min_y,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_y,
        2.0f
    );

    bpt_test::assert_near(
        bounds.min_z,
        1.0f
    );

    bpt_test::assert_near(
        bounds.max_z,
        2.0f
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Legacy API compatibility
// ---------------------------------------------------------

void test_extended_blocks_matches_legacy_api()
{
    TestVolume volume(
        7,
        6,
        5
    );

    /*
     * Deliberately irregular shape:
     *
     * main body
     */
    volume.fill_box(
        1,
        4,
        1,
        3,
        1,
        2
    );

    /*
     * asymmetric extensions
     */
    volume.set(
        5,
        2,
        1
    );

    volume.set(
        3,
        4,
        2
    );

    volume.set(
        2,
        2,
        3
    );

    constexpr float voxel_size =
        0.375f;

    auto legacy =
        build_legacy(
            volume,
            voxel_size,
            true
        );

    auto extended =
        build_extended_blocks(
            volume,
            voxel_size,
            true
        );

    bpt_test::assert_mesh_valid(
        legacy
    );

    bpt_test::assert_mesh_valid(
        extended
    );

    /*
     * This is intentionally an exact comparison.
     *
     * BPT_MESH_BLOCKS is not merely expected to look
     * similar to the historical function: it must remain
     * the exact same generated geometry.
     */
    bpt_test::assert_same_mesh(
        legacy,
        extended
    );

    bpt_free_mesh(
        &legacy
    );

    bpt_free_mesh(
        &extended
    );
}


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


int main()
{
    test_single_voxel_geometry();

    test_adjacent_voxels_remove_internal_face();

    test_extended_blocks_matches_legacy_api();

    test_blocks_is_deterministic();

    test_voxel_size_scales_geometry();

    test_center_xy_preserves_historical_coordinates();

    std::cout
        << "Block mesh tests passed."
        << std::endl;

    return 0;
}