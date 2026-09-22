#pragma once

#include "bpt_core.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>


namespace bpt_test
{


// ---------------------------------------------------------
// Test volume
// ---------------------------------------------------------

class TestVolume
{
public:
    TestVolume(
        const std::int32_t width,
        const std::int32_t depth,
        const std::int32_t height
    )
        : width_(width),
          depth_(depth),
          height_(height),
          values_(
              static_cast<std::size_t>(width)
              * static_cast<std::size_t>(depth)
              * static_cast<std::size_t>(height),
              0
          )
    {
        assert(
            width > 0
        );

        assert(
            depth > 0
        );

        assert(
            height > 0
        );
    }


    std::int32_t width() const
    {
        return width_;
    }


    std::int32_t depth() const
    {
        return depth_;
    }


    std::int32_t height() const
    {
        return height_;
    }


    std::size_t index(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        assert(
            x >= 0
            && x < width_
        );

        assert(
            y >= 0
            && y < depth_
        );

        assert(
            z >= 0
            && z < height_
        );

        return (
            (
                static_cast<std::size_t>(
                    z
                )
                * static_cast<std::size_t>(
                    depth_
                )
                + static_cast<std::size_t>(
                    y
                )
            )
            * static_cast<std::size_t>(
                width_
            )
            + static_cast<std::size_t>(
                x
            )
        );
    }


    bool occupied(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        return (
            values_[
                index(
                    x,
                    y,
                    z
                )
            ]
            != 0
        );
    }


    void set(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z,
        const bool occupied = true
    )
    {
        values_[
            index(
                x,
                y,
                z
            )
        ] = (
            occupied
            ? 1
            : 0
        );
    }


    void fill_box(
        const std::int32_t min_x,
        const std::int32_t max_x,
        const std::int32_t min_y,
        const std::int32_t max_y,
        const std::int32_t min_z,
        const std::int32_t max_z
    )
    {
        assert(
            min_x <= max_x
        );

        assert(
            min_y <= max_y
        );

        assert(
            min_z <= max_z
        );

        for (
            std::int32_t z = min_z;
            z <= max_z;
            ++z
        )
        {
            for (
                std::int32_t y = min_y;
                y <= max_y;
                ++y
            )
            {
                for (
                    std::int32_t x = min_x;
                    x <= max_x;
                    ++x
                )
                {
                    set(
                        x,
                        y,
                        z
                    );
                }
            }
        }
    }


    std::size_t occupied_count() const
    {
        return static_cast<
            std::size_t
        >(
            std::count_if(
                values_.begin(),
                values_.end(),
                [](
                    const std::uint8_t value
                )
                {
                    return (
                        value != 0
                    );
                }
            )
        );
    }


    BptVolumeResult native() const
    {
        BptVolumeResult result {};

        result.width =
            width_;

        result.depth =
            depth_;

        result.height =
            height_;

        /*
         * The native API does not mutate the input volume.
         *
         * Its historical C ABI unfortunately does not mark
         * this pointer const, so expose the test buffer here.
         */
        result.values =
            const_cast<
                std::uint8_t*
            >(
                values_.data()
            );

        result.value_count =
            values_.size();

        result.occupied_count =
            occupied_count();

        if (
            result.occupied_count
            == 0
        )
        {
            result.has_bounds =
                0;

            return result;
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

        for (
            std::int32_t z = 0;
            z < height_;
            ++z
        )
        {
            for (
                std::int32_t y = 0;
                y < depth_;
                ++y
            )
            {
                for (
                    std::int32_t x = 0;
                    x < width_;
                    ++x
                )
                {
                    if (
                        !occupied(
                            x,
                            y,
                            z
                        )
                    )
                    {
                        continue;
                    }

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

        result.has_bounds =
            1;

        result.min_x =
            min_x;

        result.max_x =
            max_x;

        result.min_y =
            min_y;

        result.max_y =
            max_y;

        result.min_z =
            min_z;

        result.max_z =
            max_z;

        return result;
    }


private:
    std::int32_t width_;
    std::int32_t depth_;
    std::int32_t height_;

    std::vector<
        std::uint8_t
    >
        values_;
};

} // namespace bpt_test
