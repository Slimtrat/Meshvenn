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



} // namespace visual_hull_test
