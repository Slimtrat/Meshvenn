#include "bpt_core.h"

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <vector>


namespace
{


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


BptProjectionInput
projection(
    const std::vector<std::uint8_t>& mask,
    const std::int32_t size,
    const float azimuth,
    const float elevation = 0.0f
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
        0;

    return result;
}


BptScanOptions
default_options()
{
    BptScanOptions options {};

    options.resolution =
        8;

    options.symmetry_x =
        0;

    options.thread_count =
        1;

    return options;
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
test_create_and_destroy_session()
{
    auto options =
        default_options();

    BptVisualHullSession* session =
        nullptr;

    const auto result =
        bpt_visual_hull_create(
            &options,
            &session
        );

    assert(
        result == BPT_OK
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
        full_mask(size);

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

    const auto result =
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        );

    assert(
        result == BPT_OK
    );

    assert(
        volume.occupied_count
        > 0
    );

    assert(
        volume.value_count
        == 8u * 8u * 8u
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
        full_mask(size);

    auto empty =
        empty_mask(size);

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

    const auto result =
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        );

    assert(
        result == BPT_OK
    );

    assert(
        volume.occupied_count
        == 0
    );

    assert(
        volume.has_bounds
        == 0
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
        full_mask(size);

    auto center =
        center_mask(size);

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

    std::size_t after_front =
        0;

    auto front =
        projection(
            full,
            size,
            0.0f
        );

    assert(
        bpt_visual_hull_apply_projection(
            session,
            &front,
            &after_front
        )
        == BPT_OK
    );

    std::size_t after_side =
        0;

    auto side =
        projection(
            center,
            size,
            90.0f
        );

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
        <= after_front
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
        full_mask(size);

    auto center =
        center_mask(size);

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

    BptVolumeResult first_snapshot {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &first_snapshot
        )
        == BPT_OK
    );

    const auto first_count =
        first_snapshot
            .occupied_count;

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

    BptVolumeResult second_snapshot {};

    assert(
        bpt_visual_hull_snapshot(
            session,
            &second_snapshot
        )
        == BPT_OK
    );

    assert(
        second_snapshot
            .occupied_count
        <= first_count
    );

    assert(
        first_snapshot
            .occupied_count
        == first_count
    );

    bpt_free_volume(
        &first_snapshot
    );

    bpt_free_volume(
        &second_snapshot
    );

    bpt_visual_hull_destroy(
        session
    );
}


void
test_multithread_matches_single_thread()
{
    constexpr std::int32_t size =
        8;

    auto full =
        full_mask(size);

    auto center =
        center_mask(size);

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
    };

    auto single =
        default_options();

    single.thread_count =
        1;

    auto multi =
        default_options();

    multi.thread_count =
        4;

    BptVolumeResult single_volume {};
    BptVolumeResult multi_volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            3,
            &single,
            &single_volume
        )
        == BPT_OK
    );

    assert(
        bpt_build_visual_hull(
            projections,
            3,
            &multi,
            &multi_volume
        )
        == BPT_OK
    );

    assert(
        single_volume
            .occupied_count
        == multi_volume
            .occupied_count
    );

    assert(
        single_volume
            .value_count
        == multi_volume
            .value_count
    );

    for (
        std::size_t index = 0;
        index < single_volume.value_count;
        ++index
    )
    {
        assert(
            single_volume.values[index]
            == multi_volume.values[index]
        );
    }

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
        8;

    auto mask =
        center_mask(size);

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
        mesh.polygon_count
        > 0
    );

    bpt_free_mesh(
        &mesh
    );

    bpt_free_volume(
        &volume
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


}


int main()
{
    std::cout
        << "BPT native tests"
        << std::endl;

    test_invalid_resolution();

    test_create_and_destroy_session();

    test_two_full_projections_keep_volume();

    test_empty_projection_removes_everything();

    test_incremental_projection_reduces_volume();

    test_snapshot_is_independent();

    test_multithread_matches_single_thread();

    test_mesh_generation();

    test_result_messages();

    test_abi_version();

    std::cout
        << "All native tests passed."
        << std::endl;

    return 0;
}