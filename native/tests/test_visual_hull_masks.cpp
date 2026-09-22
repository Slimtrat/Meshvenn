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
    const float elevation,
    const bool flip_x
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
    const std::int32_t resolution
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



} // namespace visual_hull_test
