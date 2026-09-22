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



} // namespace visual_hull_test
