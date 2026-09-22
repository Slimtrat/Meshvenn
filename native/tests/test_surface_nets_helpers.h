#pragma once

#include "bpt_core.h"
#include "test_mesh_helpers.h"

#include <cstdint>


namespace bpt_surface_nets_test
{


using bpt_test::TestVolume;


BptMeshResult build_surface_nets(
    const TestVolume& test_volume,
    float voxel_size = 1.0f,
    bool center_xy = false
);

void assert_all_quads(const BptMeshResult& mesh);

struct Vec3
{
    float x;
    float y;
    float z;
};

Vec3 vertex(const BptMeshResult& mesh, std::uint32_t index);
Vec3 subtract(const Vec3& a, const Vec3& b);
Vec3 cross(const Vec3& a, const Vec3& b);
float dot(const Vec3& a, const Vec3& b);
float length_squared(const Vec3& value);

void assert_no_degenerate_quads(const BptMeshResult& mesh);
void assert_closed_two_manifold(const BptMeshResult& mesh);

void test_single_voxel();
void test_voxel_at_minimum_boundary();
void test_voxel_at_maximum_boundary();
void test_solid_block_is_closed();
void test_disconnected_voxels();
void test_irregular_shape();
void test_hollow_box();
void test_surface_nets_is_deterministic();
void test_surface_nets_differs_from_blocks();


} // namespace bpt_surface_nets_test
