#include "test_mesh_api_results.h"

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