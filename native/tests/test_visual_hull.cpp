#include "test_visual_hull_cases.h"
#include <iostream>

using namespace visual_hull_test;

int main()
{
    std::cout
        << "BPT native tests"
        << std::endl;

    test_invalid_resolution();
    test_not_enough_projections();

    test_create_and_destroy_session();

    test_two_full_projections_keep_volume();
    test_empty_projection_removes_everything();

    test_incremental_projection_reduces_volume();
    test_snapshot_is_independent();

    test_45_degree_projection();

    test_top_projection();
    test_bottom_projection();

    test_flip_x_mirrors_volume();
    test_symmetry_x();

    test_multithread_matches_single_thread();

    test_mesh_generation();
    test_empty_mesh_generation();

    test_result_messages();
    test_abi_version();

    std::cout
        << "All native tests passed."
        << std::endl;

    return 0;
}
