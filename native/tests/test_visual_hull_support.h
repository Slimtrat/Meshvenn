#pragma once

#include "bpt_core.h"

#include <cstddef>
#include <cstdint>
#include <vector>

namespace visual_hull_test
{

std::size_t volume_index(
    const BptVolumeResult& volume,
    std::int32_t x,
    std::int32_t y,
    std::int32_t z
);

std::vector<std::uint8_t> full_mask(std::int32_t size);
std::vector<std::uint8_t> empty_mask(std::int32_t size);
std::vector<std::uint8_t> center_mask(std::int32_t size);
std::vector<std::uint8_t> left_mask(std::int32_t size);
std::vector<std::uint8_t> horizontal_band_mask(std::int32_t size);

BptProjectionInput projection(
    const std::vector<std::uint8_t>& mask,
    std::int32_t size,
    float azimuth,
    float elevation = 0.0f,
    bool flip_x = false
);

BptScanOptions default_options(std::int32_t resolution = 8);

BptVolumeResult run_session_single_projection(
    const BptProjectionInput& input,
    BptScanOptions options
);

void assert_same_volume(const BptVolumeResult& a, const BptVolumeResult& b);
void assert_x_symmetric(const BptVolumeResult& volume);
void assert_bounds_match_values(const BptVolumeResult& volume);

} // namespace visual_hull_test
