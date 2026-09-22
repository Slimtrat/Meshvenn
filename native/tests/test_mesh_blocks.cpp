#include "test_mesh_blocks_behavior.h"

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