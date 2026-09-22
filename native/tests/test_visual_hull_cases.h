#pragma once

namespace visual_hull_test
{

void test_invalid_resolution();
void test_not_enough_projections();
void test_create_and_destroy_session();
void test_two_full_projections_keep_volume();
void test_empty_projection_removes_everything();
void test_incremental_projection_reduces_volume();
void test_snapshot_is_independent();
void test_45_degree_projection();
void test_top_projection();
void test_bottom_projection();
void test_flip_x_mirrors_volume();
void test_symmetry_x();
void test_multithread_matches_single_thread();
void test_mesh_generation();
void test_empty_mesh_generation();
void test_result_messages();
void test_abi_version();

} // namespace visual_hull_test
