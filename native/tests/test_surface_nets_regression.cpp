#include "test_surface_nets_helpers.h"

#include <cassert>
#include <cmath>
#include <cstddef>

namespace bpt_surface_nets_test
{

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

} // namespace bpt_surface_nets_test
