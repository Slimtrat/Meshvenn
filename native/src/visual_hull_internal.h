#pragma once

#include "bpt_core.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace bpt_visual_hull_detail
{

struct CompiledProjection
{
    const std::uint8_t* mask =
        nullptr;

    std::int32_t width = 0;
    std::int32_t height = 0;

    float width_minus_one = 0.0f;
    float height_minus_one = 0.0f;

    float cos_az = 1.0f;
    float sin_az = 0.0f;

    float cos_el = 1.0f;
    float sin_el = 0.0f;

    float horizontal_extent = 1.0f;
    float vertical_extent = 1.0f;

    bool flip_x = false;
};


struct BoundsAccumulator
{
    bool found = false;

    std::int32_t min_x = 0;
    std::int32_t max_x = 0;

    std::int32_t min_y = 0;
    std::int32_t max_y = 0;

    std::int32_t min_z = 0;
    std::int32_t max_z = 0;


    void add(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    )
    {
        if (!found)
        {
            found = true;

            min_x = max_x = x;
            min_y = max_y = y;
            min_z = max_z = z;

            return;
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


    void merge(
        const BoundsAccumulator& other
    )
    {
        if (!other.found)
        {
            return;
        }

        if (!found)
        {
            *this = other;
            return;
        }

        min_x =
            std::min(
                min_x,
                other.min_x
            );

        max_x =
            std::max(
                max_x,
                other.max_x
            );

        min_y =
            std::min(
                min_y,
                other.min_y
            );

        max_y =
            std::max(
                max_y,
                other.max_y
            );

        min_z =
            std::min(
                min_z,
                other.min_z
            );

        max_z =
            std::max(
                max_z,
                other.max_z
            );
    }
};


struct WorkerResult
{
    std::size_t begin = 0;
    std::size_t survivor_count = 0;

    BoundsAccumulator bounds;
};

std::int32_t resolve_thread_count(std::int32_t requested);
std::size_t resolve_worker_count(std::size_t alive_count, std::int32_t thread_limit);
float grid_to_normalized(std::int32_t value, std::int32_t size);
BptResultCode validate_options(const BptScanOptions* options);
BptResultCode validate_projection(const BptProjectionInput* projection);
CompiledProjection compile_projection(const BptProjectionInput& projection);
void write_volume_bounds(const BoundsAccumulator& bounds, BptVolumeResult* volume);

} // namespace bpt_visual_hull_detail


struct BptVisualHullSession
{
    BptScanOptions options {};

    std::int32_t width = 0;
    std::int32_t depth = 0;
    std::int32_t height = 0;

    /*
     * Dense voxel storage is intentionally
     * NOT kept during reconstruction.
     *
     * The list continuously shrinks as
     * projections are applied.
     */
    std::vector<
        std::uint32_t
    > alive_indices;

    std::vector<float>
        normalized_coords;

    bpt_visual_hull_detail::BoundsAccumulator bounds;

    std::int32_t thread_limit = 1;
};
