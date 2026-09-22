#include "visual_hull_internal.h"

#include <algorithm>
#include <thread>

namespace
{

/*
 * Do not spawn a large number of worker threads
 * once only a small number of voxels remain.
 */
constexpr std::size_t
    kMinVoxelsPerWorker =
        32768;

} // namespace

namespace bpt_visual_hull_detail
{

std::int32_t resolve_thread_count(
    const std::int32_t requested
)
{
    if (requested > 0)
    {
        return std::max(
            1,
            requested
        );
    }

    const auto detected =
        std::thread::hardware_concurrency();

    if (detected == 0)
    {
        return 1;
    }

    return static_cast<
        std::int32_t
    >(
        detected
    );
}


std::size_t resolve_worker_count(
    const std::size_t alive_count,
    const std::int32_t thread_limit
)
{
    if (alive_count == 0)
    {
        return 0;
    }

    const auto useful_workers =
        std::max<
            std::size_t
        >(
            1,
            (
                alive_count
                + kMinVoxelsPerWorker
                - 1
            )
            / kMinVoxelsPerWorker
        );

    return std::min(
        alive_count,
        std::min(
            useful_workers,
            static_cast<
                std::size_t
            >(
                std::max(
                    1,
                    thread_limit
                )
            )
        )
    );
}

float grid_to_normalized(
    const std::int32_t value,
    const std::int32_t size
)
{
    if (size <= 1)
    {
        return 0.0f;
    }

    return (
        (
            static_cast<float>(
                value
            )
            / static_cast<float>(
                size - 1
            )
        )
        * 2.0f
        - 1.0f
    );
}

BptResultCode validate_options(
    const BptScanOptions* options
)
{
    if (options == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        options->resolution < 8
        || options->resolution > 256
    )
    {
        return (
            BPT_ERROR_INVALID_RESOLUTION
        );
    }

    return BPT_OK;
}

void write_volume_bounds(
    const BoundsAccumulator& bounds,
    BptVolumeResult* volume
)
{
    if (!bounds.found)
    {
        volume->has_bounds = 0;

        volume->min_x = 0;
        volume->max_x = 0;

        volume->min_y = 0;
        volume->max_y = 0;

        volume->min_z = 0;
        volume->max_z = 0;

        return;
    }

    volume->has_bounds = 1;

    volume->min_x =
        bounds.min_x;

    volume->max_x =
        bounds.max_x;

    volume->min_y =
        bounds.min_y;

    volume->max_y =
        bounds.max_y;

    volume->min_z =
        bounds.min_z;

    volume->max_z =
        bounds.max_z;
}

} // namespace bpt_visual_hull_detail
