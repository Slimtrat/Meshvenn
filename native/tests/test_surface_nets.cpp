#include "test_surface_nets_helpers.h"

#include <iostream>

int main()
{
    using namespace bpt_surface_nets_test;
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
