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
// Valid reference volume
// ---------------------------------------------------------

TestVolume single_voxel_volume()
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

    return volume;
}


// ---------------------------------------------------------
// Null arguments
// ---------------------------------------------------------

void test_extended_api_rejects_null_volume()
{
    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            nullptr,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


void test_extended_api_rejects_null_options()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            nullptr,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


void test_extended_api_rejects_null_output()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS
        );

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            nullptr
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


// ---------------------------------------------------------
// Legacy null output
// ---------------------------------------------------------

void test_legacy_api_rejects_null_output()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            0,
            nullptr
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


// ---------------------------------------------------------
// Invalid voxel size
// ---------------------------------------------------------

void test_legacy_api_rejects_zero_voxel_size()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            0.0f,
            0,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );

    assert(
        mesh.vertices
        == nullptr
    );

    assert(
        mesh.vertex_float_count
        == 0
    );

    assert(
        mesh.indices
        == nullptr
    );

    assert(
        mesh.index_count
        == 0
    );

    assert(
        mesh.polygon_count
        == 0
    );
}


void test_extended_api_rejects_zero_voxel_size()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS,
            0.0f
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


void test_extended_api_rejects_negative_voxel_size()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS,
            -1.0f
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


// ---------------------------------------------------------
// Invalid mesh mode
// ---------------------------------------------------------

void test_extended_api_rejects_unknown_mode()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    BptMeshOptions options {};

    options.voxel_size =
        1.0f;

    options.mode =
        9999;

    options.center_xy =
        0;

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );

    assert(
        mesh.vertices
        == nullptr
    );

    assert(
        mesh.vertex_float_count
        == 0
    );

    assert(
        mesh.polygon_count
        == 0
    );
}


// ---------------------------------------------------------
// Invalid volume dimensions
// ---------------------------------------------------------

void test_rejects_zero_width()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    volume.width =
        0;

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


void test_rejects_value_count_mismatch()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    assert(
        volume.value_count
        > 0
    );

    --volume.value_count;

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


void test_rejects_null_values()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    volume.values =
        nullptr;

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );
}


// ---------------------------------------------------------
// Empty volume
// ---------------------------------------------------------

void assert_empty_mesh(
    const BptMeshResult& mesh
)
{
    assert(
        mesh.vertices
        == nullptr
    );

    assert(
        mesh.vertex_float_count
        == 0
    );

    assert(
        mesh.indices
        == nullptr
    );

    assert(
        mesh.index_count
        == 0
    );

    assert(
        mesh.polygon_starts
        == nullptr
    );

    assert(
        mesh.polygon_sizes
        == nullptr
    );

    assert(
        mesh.polygon_count
        == 0
    );
}


void test_empty_volume_blocks()
{
    TestVolume test_volume(
        4,
        4,
        4
    );

    auto volume =
        test_volume.native();

    assert(
        volume.occupied_count
        == 0
    );

    assert(
        volume.has_bounds
        == 0
    );

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_BLOCKS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        == BPT_OK
    );

    assert_empty_mesh(
        mesh
    );

    bpt_free_mesh(
        &mesh
    );
}


void test_empty_volume_surface_nets()
{
    TestVolume test_volume(
        4,
        4,
        4
    );

    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        == BPT_OK
    );

    assert_empty_mesh(
        mesh
    );

    bpt_free_mesh(
        &mesh
    );
}


// ---------------------------------------------------------
// Output is reset before validation
// ---------------------------------------------------------

void test_error_resets_output_metadata()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    BptMeshOptions options {};

    options.voxel_size =
        1.0f;

    options.mode =
        123456;

    BptMeshResult mesh {};

    /*
     * Deliberately dirty metadata.
     *
     * Pointers remain null so this test does not create
     * ownership ambiguity or leak memory.
     */
    mesh.vertex_float_count =
        42;

    mesh.index_count =
        43;

    mesh.polygon_count =
        44;

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        ==
        BPT_ERROR_INVALID_ARGUMENT
    );

    assert_empty_mesh(
        mesh
    );
}


// ---------------------------------------------------------
// Free mesh contract
// ---------------------------------------------------------

void test_free_mesh_resets_result()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    auto options =
        bpt_test::mesh_options(
            BPT_MESH_SURFACE_NETS
        );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh_ex(
            &volume,
            &options,
            &mesh
        )
        == BPT_OK
    );

    assert(
        mesh.vertex_float_count
        > 0
    );

    bpt_free_mesh(
        &mesh
    );

    assert_empty_mesh(
        mesh
    );

    /*
     * Free must remain safe when called repeatedly.
     */
    bpt_free_mesh(
        &mesh
    );

    assert_empty_mesh(
        mesh
    );
}


// ---------------------------------------------------------
// Both public modes are accepted
// ---------------------------------------------------------

void test_public_mesh_modes_are_accepted()
{
    auto test_volume =
        single_voxel_volume();

    auto volume =
        test_volume.native();

    for (
        const auto mode : {
            BPT_MESH_BLOCKS,
            BPT_MESH_SURFACE_NETS,
        }
    )
    {
        auto options =
            bpt_test::mesh_options(
                mode
            );

        BptMeshResult mesh {};

        assert(
            bpt_build_surface_mesh_ex(
                &volume,
                &options,
                &mesh
            )
            == BPT_OK
        );

        bpt_test::assert_mesh_valid(
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

        bpt_free_mesh(
            &mesh
        );
    }
}


// ---------------------------------------------------------
// ABI
// ---------------------------------------------------------

void test_abi_version_remains_one()
{
    /*
     * This PR adds:
     *
     * - a new enum
     * - a new independent options struct
     * - a new exported function
     *
     * Existing public layouts/signatures remain intact,
     * so ABI 1 remains load-compatible.
     */
    assert(
        bpt_abi_version()
        == 1u
    );
}


} // namespace


int main()
{
    test_extended_api_rejects_null_volume();

    test_extended_api_rejects_null_options();

    test_extended_api_rejects_null_output();

    test_legacy_api_rejects_null_output();

    test_legacy_api_rejects_zero_voxel_size();

    test_extended_api_rejects_zero_voxel_size();

    test_extended_api_rejects_negative_voxel_size();

    test_extended_api_rejects_unknown_mode();

    test_rejects_zero_width();

    test_rejects_value_count_mismatch();

    test_rejects_null_values();

    test_empty_volume_blocks();

    test_empty_volume_surface_nets();

    test_error_resets_output_metadata();

    test_free_mesh_resets_result();

    test_public_mesh_modes_are_accepted();

    test_abi_version_remains_one();

    std::cout
        << "Mesh API tests passed."
        << std::endl;

    return 0;
}