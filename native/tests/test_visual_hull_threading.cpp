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



} // namespace visual_hull_test
