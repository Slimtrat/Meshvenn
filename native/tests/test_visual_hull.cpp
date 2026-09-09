#include "bpt_core.h"

#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <vector>


namespace
{


std::size_t volume_index(
    const BptVolumeResult& volume,
    const std::int32_t x,
    const std::int32_t y,
    const std::int32_t z
)
{
    return (
        static_cast<std::size_t>(z)
        * static_cast<std::size_t>(volume.depth)
        * static_cast<std::size_t>(volume.width)
        + static_cast<std::size_t>(y)
        * static_cast<std::size_t>(volume.width)
        + static_cast<std::size_t>(x)
    );
}


std::vector<std::uint8_t>
full_mask(
    const std::int32_t size
)
{
    return std::vector<std::uint8_t>(
        static_cast<std::size_t>(
            size * size
        ),
        1
    );
}


std::vector<std::uint8_t>
empty_mask(
    const std::int32_t size
)
{
    return std::vector<std::uint8_t>(
        static_cast<std::size_t>(
            size * size
        ),
        0
    );
}


std::vector<std::uint8_t>
center_mask(
    const std::int32_t size
)
{
    std::vector<std::uint8_t> result(
        static_cast<std::size_t>(
            size * size
        ),
        0
    );

    const auto start =
        size / 4;

    const auto end =
        size - start;

    for (
        std::int32_t y = start;
        y < end;
        ++y
    )
    {
        for (
            std::int32_t x = start;
            x < end;
            ++x
        )
        {
            result[
                static_cast<std::size_t>(
                    y * size + x
                )
            ] = 1;
        }
    }

    return result;
}


std::vector<std::uint8_t>
left_mask(
    const std::int32_t size
)
{
    std::vector<std::uint8_t> result(
        static_cast<std::size_t>(
            size * size
        ),
        0
    );

    for (
        std::int32_t y = 0;
        y < size;
        ++y
    )
    {
        for (
            std::int32_t x = 0;
            x < size / 2;
            ++x
        )
        {
            result[
                static_cast<std::size_t>(
                    y * size + x
                )
            ] = 1;
        }
    }

    return result;
}


std::vector<std::uint8_t>
horizontal_band_mask(
    const std::int32_t size
)
{
    std::vector<std::uint8_t> result(
        static_cast<std::size_t>(
            size * size
        ),
        0
    );

    const auto start =
        size / 3;

    const auto end =
        size - start;

    for (
        std::int32_t y = start;
        y < end;
        ++y
    )
    {
        for (
            std::int32_t x = 0;
            x < size;
            ++x
        )
        {
            result[
                static_cast<std::size_t>(
                    y * size + x
                )
            ] = 1;
        }
    }

    return result;
}


BptProjectionInput
projection(
    const std::vector<std::uint8_t>& mask,
    const std::int32_t size,
    const float azimuth,
    const float elevation = 0.0f,
    const bool flip_x = false
)
{
    BptProjectionInput result {};

    result.mask =
        mask.data();

    result.width =
        size;

    result.height =
        size;

    result.azimuth_degrees =
        azimuth;

    result.elevation_degrees =
        elevation;

    result.flip_x =
        flip_x
        ? 1
        : 0;

    return result;
}


BptScanOptions
default_options(
    const std::int32_t resolution = 8
)
{
    BptScanOptions options {};

    options.resolution =
        resolution;

    options.symmetry_x =
        0;

    options.thread_count =
        1;

    return options;
}


BptVolumeResult
run_session_single_projection(
    const BptProjectionInput& input,
    BptScanOptions options
)
{
    BptVisualHullSession* session =
        nullptr;

    assert(
        bpt_visual_hull_create(
            &options,
            &session
        )
        == BPT_OK
    );

    assert(
        session != nullptr
    );

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &input,
            nullptr
        )
        == BPT_OK
    );

    BptVolumeResult volume {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &volume
        )
        == BPT_OK
    );

    bpt_visual_hull_destroy(
        session
    );

    return volume;
}


void assert_same_volume(
    const BptVolumeResult& a,
    const BptVolumeResult& b
)
{
    assert(
        a.width == b.width
    );

    assert(
        a.depth == b.depth
    );

    assert(
        a.height == b.height
    );

    assert(
        a.value_count
        == b.value_count
    );

    assert(
        a.occupied_count
        == b.occupied_count
    );

    for (
        std::size_t index = 0;
        index < a.value_count;
        ++index
    )
    {
        assert(
            a.values[index]
            == b.values[index]
        );
    }
}


void assert_x_symmetric(
    const BptVolumeResult& volume
)
{
    for (
        std::int32_t z = 0;
        z < volume.height;
        ++z
    )
    {
        for (
            std::int32_t y = 0;
            y < volume.depth;
            ++y
        )
        {
            for (
                std::int32_t x = 0;
                x < volume.width;
                ++x
            )
            {
                const auto mirror_x =
                    volume.width
                    - 1
                    - x;

                assert(
                    volume.values[
                        volume_index(
                            volume,
                            x,
                            y,
                            z
                        )
                    ]
                    ==
                    volume.values[
                        volume_index(
                            volume,
                            mirror_x,
                            y,
                            z
                        )
                    ]
                );
            }
        }
    }
}


void assert_bounds_match_values(
    const BptVolumeResult& volume
)
{
    if (
        volume.occupied_count == 0
    )
    {
        assert(
            volume.has_bounds == 0
        );

        return;
    }

    std::int32_t min_x =
        std::numeric_limits<
            std::int32_t
        >::max();

    std::int32_t min_y =
        min_x;

    std::int32_t min_z =
        min_x;

    std::int32_t max_x =
        std::numeric_limits<
            std::int32_t
        >::min();

    std::int32_t max_y =
        max_x;

    std::int32_t max_z =
        max_x;

    std::size_t count =
        0;

    for (
        std::int32_t z = 0;
        z < volume.height;
        ++z
    )
    {
        for (
            std::int32_t y = 0;
            y < volume.depth;
            ++y
        )
        {
            for (
                std::int32_t x = 0;
                x < volume.width;
                ++x
            )
            {
                if (
                    volume.values[
                        volume_index(
                            volume,
                            x,
                            y,
                            z
                        )
                    ]
                    == 0
                )
                {
                    continue;
                }

                ++count;

                min_x =
                    std::min(
                        min_x,
                        x
                    );

                max_x =
                    std::max(
                        max_x,
                        x
                    );

                min_y =
                    std::min(
                        min_y,
                        y
                    );

                max_y =
                    std::max(
                        max_y,
                        y
                    );

                min_z =
                    std::min(
                        min_z,
                        z
                    );

                max_z =
                    std::max(
                        max_z,
                        z
                    );
            }
        }
    }

    assert(
        count
        == volume.occupied_count
    );

    assert(
        volume.has_bounds != 0
    );

    assert(
        volume.min_x == min_x
    );

    assert(
        volume.max_x == max_x
    );

    assert(
        volume.min_y == min_y
    );

    assert(
        volume.max_y == max_y
    );

    assert(
        volume.min_z == min_z
    );

    assert(
        volume.max_z == max_z
    );
}


void
test_invalid_resolution()
{
    auto options =
        default_options();

    options.resolution =
        4;

    BptVisualHullSession* session =
        nullptr;

    const auto result =
        bpt_visual_hull_create(
            &options,
            &session
        );

    assert(
        result
        == BPT_ERROR_INVALID_RESOLUTION
    );

    assert(
        session == nullptr
    );
}


void
test_not_enough_projections()
{
    constexpr std::int32_t size =
        8;

    auto mask =
        full_mask(
            size
        );

    const auto input =
        projection(
            mask,
            size,
            0.0f
        );

    auto options =
        default_options();

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            &input,
            1,
            &options,
            &volume
        )
        == BPT_ERROR_NOT_ENOUGH_PROJECTIONS
    );
}


void
test_create_and_destroy_session()
{
    auto options =
        default_options();

    BptVisualHullSession* session =
        nullptr;

    assert(
        bpt_visual_hull_create(
            &options,
            &session
        )
        == BPT_OK
    );

    assert(
        session != nullptr
    );

    bpt_visual_hull_destroy(
        session
    );
}


void
test_two_full_projections_keep_volume()
{
    constexpr std::int32_t size =
        8;

    auto mask =
        full_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            mask,
            size,
            0.0f
        ),
        projection(
            mask,
            size,
            90.0f
        ),
    };

    auto options =
        default_options();

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        == 8u * 8u * 8u
    );

    assert(
        volume.value_count
        == 8u * 8u * 8u
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );
}


void
test_empty_projection_removes_everything()
{
    constexpr std::int32_t size =
        8;

    auto full =
        full_mask(
            size
        );

    auto empty =
        empty_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            full,
            size,
            0.0f
        ),
        projection(
            empty,
            size,
            90.0f
        ),
    };

    auto options =
        default_options();

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        == 0
    );

    assert(
        volume.has_bounds
        == 0
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );
}


void
test_incremental_projection_reduces_volume()
{
    constexpr std::int32_t size =
        8;

    auto full =
        full_mask(
            size
        );

    auto center =
        center_mask(
            size
        );

    auto options =
        default_options();

    BptVisualHullSession* session =
        nullptr;

    assert(
        bpt_visual_hull_create(
            &options,
            &session
        )
        == BPT_OK
    );

    auto front =
        projection(
            full,
            size,
            0.0f
        );

    std::size_t after_front =
        0;

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &front,
            &after_front
        )
        == BPT_OK
    );

    auto side =
        projection(
            center,
            size,
            90.0f
        );

    std::size_t after_side =
        0;

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &side,
            &after_side
        )
        == BPT_OK
    );

    assert(
        after_side
        < after_front
    );

    BptVolumeResult volume {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        == after_side
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );

    bpt_visual_hull_destroy(
        session
    );
}


void
test_snapshot_is_independent()
{
    constexpr std::int32_t size =
        8;

    auto full =
        full_mask(
            size
        );

    auto center =
        center_mask(
            size
        );

    auto options =
        default_options();

    BptVisualHullSession* session =
        nullptr;

    assert(
        bpt_visual_hull_create(
            &options,
            &session
        )
        == BPT_OK
    );

    auto front =
        projection(
            full,
            size,
            0.0f
        );

    auto side =
        projection(
            full,
            size,
            90.0f
        );

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &front,
            nullptr
        )
        == BPT_OK
    );

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &side,
            nullptr
        )
        == BPT_OK
    );

    BptVolumeResult first {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &first
        )
        == BPT_OK
    );

    const auto first_count =
        first.occupied_count;

    auto back =
        projection(
            center,
            size,
            180.0f
        );

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &back,
            nullptr
        )
        == BPT_OK
    );

    BptVolumeResult second {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &second
        )
        == BPT_OK
    );

    assert(
        second.occupied_count
        <= first_count
    );

    assert(
        first.occupied_count
        == first_count
    );

    assert_bounds_match_values(
        first
    );

    assert_bounds_match_values(
        second
    );

    bpt_free_volume(
        &first
    );

    bpt_free_volume(
        &second
    );

    bpt_visual_hull_destroy(
        session
    );
}


void
test_45_degree_projection()
{
    constexpr std::int32_t size =
        16;

    auto full =
        full_mask(
            size
        );

    auto center =
        center_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            full,
            size,
            0.0f
        ),
        projection(
            center,
            size,
            45.0f
        ),
    };

    auto options =
        default_options(
            16
        );

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        > 0
    );

    assert(
        volume.occupied_count
        < 16u * 16u * 16u
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );
}


void
test_top_projection()
{
    constexpr std::int32_t size =
        16;

    auto full =
        full_mask(
            size
        );

    auto band =
        horizontal_band_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            full,
            size,
            0.0f
        ),
        projection(
            band,
            size,
            0.0f,
            90.0f
        ),
    };

    auto options =
        default_options(
            16
        );

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        > 0
    );

    assert(
        volume.occupied_count
        < 16u * 16u * 16u
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );
}


void
test_bottom_projection()
{
    constexpr std::int32_t size =
        16;

    auto full =
        full_mask(
            size
        );

    auto center =
        center_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            full,
            size,
            0.0f
        ),
        projection(
            center,
            size,
            0.0f,
            -90.0f
        ),
    };

    auto options =
        default_options(
            16
        );

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    assert(
        volume.occupied_count
        > 0
    );

    assert_bounds_match_values(
        volume
    );

    bpt_free_volume(
        &volume
    );
}


void
test_flip_x_mirrors_volume()
{
    constexpr std::int32_t size =
        16;

    auto mask =
        left_mask(
            size
        );

    auto normal_projection =
        projection(
            mask,
            size,
            0.0f,
            0.0f,
            false
        );

    auto flipped_projection =
        projection(
            mask,
            size,
            0.0f,
            0.0f,
            true
        );

    auto options =
        default_options(
            16
        );

    auto normal =
        run_session_single_projection(
            normal_projection,
            options
        );

    auto flipped =
        run_session_single_projection(
            flipped_projection,
            options
        );

    assert(
        normal.occupied_count
        == flipped.occupied_count
    );

    for (
        std::int32_t z = 0;
        z < normal.height;
        ++z
    )
    {
        for (
            std::int32_t y = 0;
            y < normal.depth;
            ++y
        )
        {
            for (
                std::int32_t x = 0;
                x < normal.width;
                ++x
            )
            {
                const auto mirror_x =
                    normal.width
                    - 1
                    - x;

                assert(
                    normal.values[
                        volume_index(
                            normal,
                            x,
                            y,
                            z
                        )
                    ]
                    ==
                    flipped.values[
                        volume_index(
                            flipped,
                            mirror_x,
                            y,
                            z
                        )
                    ]
                );
            }
        }
    }

    bpt_free_volume(
        &normal
    );

    bpt_free_volume(
        &flipped
    );
}


void
test_symmetry_x()
{
    constexpr std::int32_t size =
        16;

    auto mask =
        left_mask(
            size
        );

    auto input =
        projection(
            mask,
            size,
            0.0f
        );

    auto normal_options =
        default_options(
            16
        );

    auto symmetry_options =
        normal_options;

    symmetry_options.symmetry_x =
        1;

    auto normal =
        run_session_single_projection(
            input,
            normal_options
        );

    auto symmetric =
        run_session_single_projection(
            input,
            symmetry_options
        );

    assert(
        symmetric.occupied_count
        <= normal.occupied_count
    );

    assert_x_symmetric(
        symmetric
    );

    assert_bounds_match_values(
        symmetric
    );

    bpt_free_volume(
        &normal
    );

    bpt_free_volume(
        &symmetric
    );
}


void
test_multithread_matches_single_thread()
{
    constexpr std::int32_t size =
        32;

    auto full =
        full_mask(
            size
        );

    auto center =
        center_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            full,
            size,
            0.0f
        ),
        projection(
            center,
            size,
            90.0f
        ),
        projection(
            center,
            size,
            45.0f
        ),
        projection(
            center,
            size,
            180.0f
        ),
    };

    auto single =
        default_options(
            32
        );

    single.thread_count =
        1;

    auto multi =
        single;

    multi.thread_count =
        4;

    BptVolumeResult single_volume {};
    BptVolumeResult multi_volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            4,
            &single,
            &single_volume
        )
        == BPT_OK
    );

    assert(
        bpt_build_visual_hull(
            projections,
            4,
            &multi,
            &multi_volume
        )
        == BPT_OK
    );

    assert_same_volume(
        single_volume,
        multi_volume
    );

    assert_bounds_match_values(
        single_volume
    );

    assert_bounds_match_values(
        multi_volume
    );

    bpt_free_volume(
        &single_volume
    );

    bpt_free_volume(
        &multi_volume
    );
}


void
test_mesh_generation()
{
    constexpr std::int32_t size =
        16;

    auto mask =
        center_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            mask,
            size,
            0.0f
        ),
        projection(
            mask,
            size,
            90.0f
        ),
    };

    auto options =
        default_options(
            16
        );

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            1,
            &mesh
        )
        == BPT_OK
    );

    assert(
        mesh.vertex_float_count
        > 0
    );

    assert(
        mesh.vertex_float_count
        % 3
        == 0
    );

    assert(
        mesh.index_count
        > 0
    );

    assert(
        mesh.index_count
        % 4
        == 0
    );

    assert(
        mesh.polygon_count
        > 0
    );

    assert(
        mesh.index_count
        == mesh.polygon_count
        * 4
    );

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

        assert(
            mesh.polygon_starts[
                polygon
            ]
            == polygon * 4
        );
    }

    bpt_free_mesh(
        &mesh
    );

    bpt_free_volume(
        &volume
    );
}


void
test_empty_mesh_generation()
{
    constexpr std::int32_t size =
        8;

    std::vector<std::uint8_t> values(
        size * size * size,
        0
    );

    BptVolumeResult volume {};

    volume.width =
        size;

    volume.depth =
        size;

    volume.height =
        size;

    volume.values =
        values.data();

    volume.value_count =
        values.size();

    volume.occupied_count =
        0;

    volume.has_bounds =
        0;

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            1,
            &mesh
        )
        == BPT_OK
    );

    assert(
        mesh.vertex_float_count
        == 0
    );

    assert(
        mesh.index_count
        == 0
    );

    assert(
        mesh.polygon_count
        == 0
    );

    bpt_free_mesh(
        &mesh
    );
}


void
test_result_messages()
{
    assert(
        bpt_result_message(
            BPT_OK
        )
        != nullptr
    );

    assert(
        bpt_result_message(
            BPT_ERROR_INVALID_ARGUMENT
        )
        != nullptr
    );

    assert(
        bpt_result_message(
            BPT_ERROR_INTERNAL
        )
        != nullptr
    );
}


void
test_abi_version()
{
    assert(
        bpt_abi_version()
        == 1u
    );
}


} // namespace


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