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

} // namespace
