#include "test_visual_hull_cases.h"
#include "test_visual_hull_support.h"
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <vector>

namespace visual_hull_test
{

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



} // namespace visual_hull_test
