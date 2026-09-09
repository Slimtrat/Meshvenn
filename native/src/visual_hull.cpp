#include "bpt_core.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <future>
#include <memory>
#include <new>
#include <thread>
#include <utility>
#include <vector>


namespace
{


constexpr float kEpsilon = 1e-9f;


struct CompiledProjection
{
    const std::uint8_t* mask = nullptr;

    std::int32_t width = 0;
    std::int32_t height = 0;

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

        min_x = std::min(min_x, x);
        max_x = std::max(max_x, x);

        min_y = std::min(min_y, y);
        max_y = std::max(max_y, y);

        min_z = std::min(min_z, z);
        max_z = std::max(max_z, z);
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

        min_x = std::min(min_x, other.min_x);
        max_x = std::max(max_x, other.max_x);

        min_y = std::min(min_y, other.min_y);
        max_y = std::max(max_y, other.max_y);

        min_z = std::min(min_z, other.min_z);
        max_z = std::max(max_z, other.max_z);
    }
};


struct WorkerResult
{
    std::vector<std::uint32_t> alive_indices;
    BoundsAccumulator bounds;
};


std::int32_t resolve_thread_count(
    const std::int32_t requested
)
{
    if (requested > 0)
    {
        return requested;
    }

    const auto detected = std::thread::hardware_concurrency();

    if (detected == 0)
    {
        return 1;
    }

    return static_cast<std::int32_t>(
        detected
    );
}


float radians(
    const float degrees
)
{
    constexpr float kPi =
        3.14159265358979323846f;

    return degrees * kPi / 180.0f;
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
        static_cast<float>(value)
        / static_cast<float>(size - 1)
    ) * 2.0f - 1.0f;
}


BptResultCode validate_options(
    const BptScanOptions* options
)
{
    if (options == nullptr)
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (
        options->resolution < 8
        || options->resolution > 256
    )
    {
        return BPT_ERROR_INVALID_RESOLUTION;
    }

    return BPT_OK;
}


BptResultCode validate_projection(
    const BptProjectionInput* projection
)
{
    if (projection == nullptr)
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (projection->mask == nullptr)
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (
        projection->width <= 0
        || projection->height <= 0
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    return BPT_OK;
}


CompiledProjection compile_projection(
    const BptProjectionInput& projection
)
{
    const float azimuth =
        radians(
            projection.azimuth_degrees
        );

    const float elevation =
        radians(
            projection.elevation_degrees
        );

    const float cos_az_abs =
        std::abs(
            std::cos(azimuth)
        );

    const float sin_az_abs =
        std::abs(
            std::sin(azimuth)
        );

    const float horizontal_extent =
        std::max(
            cos_az_abs + sin_az_abs,
            kEpsilon
        );

    const float cos_el_abs =
        std::abs(
            std::cos(elevation)
        );

    const float sin_el_abs =
        std::abs(
            std::sin(elevation)
        );

    const float vertical_extent =
        std::max(
            horizontal_extent * sin_el_abs
                + cos_el_abs,
            kEpsilon
        );

    CompiledProjection result;

    result.mask =
        projection.mask;

    result.width =
        projection.width;

    result.height =
        projection.height;

    result.cos_az =
        std::cos(-azimuth);

    result.sin_az =
        std::sin(-azimuth);

    result.cos_el =
        std::cos(-elevation);

    result.sin_el =
        std::sin(-elevation);

    result.horizontal_extent =
        horizontal_extent;

    result.vertical_extent =
        vertical_extent;

    result.flip_x =
        projection.flip_x != 0;

    return result;
}


bool sample_projection(
    const CompiledProjection& projection,
    const float nx,
    const float ny,
    const float nz
)
{
    const float x1 =
        nx * projection.cos_az
        - ny * projection.sin_az;

    const float y1 =
        nx * projection.sin_az
        + ny * projection.cos_az;

    const float z2 =
        y1 * projection.sin_el
        + nz * projection.cos_el;

    float u =
        (
            x1
            / projection.horizontal_extent
            + 1.0f
        ) * 0.5f;

    const float v =
        (
            z2
            / projection.vertical_extent
            + 1.0f
        ) * 0.5f;

    if (projection.flip_x)
    {
        u =
            1.0f - u;
    }

    if (
        u < 0.0f
        || u > 1.0f
        || v < 0.0f
        || v > 1.0f
    )
    {
        return false;
    }

    const auto x =
        std::min(
            static_cast<std::int32_t>(
                u
                * static_cast<float>(
                    projection.width - 1
                )
                + 0.5f
            ),
            projection.width - 1
        );

    const auto y =
        std::min(
            static_cast<std::int32_t>(
                v
                * static_cast<float>(
                    projection.height - 1
                )
                + 0.5f
            ),
            projection.height - 1
        );

    const auto index =
        static_cast<std::size_t>(
            y
        )
        * static_cast<std::size_t>(
            projection.width
        )
        + static_cast<std::size_t>(
            x
        );

    return projection.mask[index] != 0;
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


}


struct BptVisualHullSession
{
    BptScanOptions options {};

    std::int32_t width = 0;
    std::int32_t depth = 0;
    std::int32_t height = 0;

    std::vector<std::uint8_t> values;
    std::vector<std::uint32_t> alive_indices;

    std::vector<float> normalized_coords;

    BoundsAccumulator bounds;
};


extern "C"
{


BptResultCode
bpt_visual_hull_create(
    const BptScanOptions* options,
    BptVisualHullSession** out_session
)
{
    if (
        options == nullptr
        || out_session == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    *out_session = nullptr;

    const auto validation =
        validate_options(options);

    if (validation != BPT_OK)
    {
        return validation;
    }

    try
    {
        auto session =
            std::make_unique<
                BptVisualHullSession
            >();

        session->options =
            *options;

        session->width =
            options->resolution;

        session->depth =
            options->resolution;

        session->height =
            options->resolution;

        const auto resolution =
            static_cast<std::size_t>(
                options->resolution
            );

        const auto voxel_count =
            resolution
            * resolution
            * resolution;

        session->values.assign(
            voxel_count,
            1
        );

        session->alive_indices.resize(
            voxel_count
        );

        for (
            std::size_t index = 0;
            index < voxel_count;
            ++index
        )
        {
            session->alive_indices[index] =
                static_cast<std::uint32_t>(
                    index
                );
        }

        session->normalized_coords.resize(
            resolution
        );

        for (
            std::int32_t index = 0;
            index < options->resolution;
            ++index
        )
        {
            session->normalized_coords[
                static_cast<std::size_t>(
                    index
                )
            ] =
                grid_to_normalized(
                    index,
                    options->resolution
                );
        }

        session->bounds.found = true;

        session->bounds.min_x = 0;
        session->bounds.max_x =
            options->resolution - 1;

        session->bounds.min_y = 0;
        session->bounds.max_y =
            options->resolution - 1;

        session->bounds.min_z = 0;
        session->bounds.max_z =
            options->resolution - 1;

        *out_session =
            session.release();

        return BPT_OK;
    }
    catch (const std::bad_alloc&)
    {
        return BPT_ERROR_ALLOCATION_FAILED;
    }
    catch (...)
    {
        return BPT_ERROR_INTERNAL;
    }
}


BptResultCode
bpt_visual_hull_apply_projection(
    BptVisualHullSession* session,
    const BptProjectionInput* projection,
    std::size_t* out_surviving_voxels
)
{
    if (
        session == nullptr
        || projection == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    const auto validation =
        validate_projection(projection);

    if (validation != BPT_OK)
    {
        return validation;
    }

    try
    {
        if (
            session->alive_indices.empty()
        )
        {
            session->bounds =
                BoundsAccumulator {};

            if (
                out_surviving_voxels
                != nullptr
            )
            {
                *out_surviving_voxels = 0;
            }

            return BPT_OK;
        }

        const auto compiled =
            compile_projection(
                *projection
            );

        const auto thread_count =
            std::max(
                1,
                resolve_thread_count(
                    session
                        ->options
                        .thread_count
                )
            );

        const auto alive_count =
            session
                ->alive_indices
                .size();

        const auto worker_count =
            std::min<
                std::size_t
            >(
                static_cast<
                    std::size_t
                >(
                    thread_count
                ),
                alive_count
            );

        const auto chunk_size =
            (
                alive_count
                + worker_count
                - 1
            )
            / worker_count;

        const auto width =
            session->width;

        const auto depth =
            session->depth;

        const auto plane =
            static_cast<std::uint32_t>(
                width
                * depth
            );

        std::vector<
            std::future<
                WorkerResult
            >
        > futures;

        futures.reserve(
            worker_count
        );

        for (
            std::size_t worker = 0;
            worker < worker_count;
            ++worker
        )
        {
            const auto begin =
                worker * chunk_size;

            const auto end =
                std::min(
                    begin + chunk_size,
                    alive_count
                );

            if (begin >= end)
            {
                continue;
            }

            futures.emplace_back(
                std::async(
                    std::launch::async,
                    [
                        session,
                        compiled,
                        begin,
                        end,
                        width,
                        depth,
                        plane
                    ]()
                    {
                        WorkerResult result;

                        result
                            .alive_indices
                            .reserve(
                                end - begin
                            );

                        const auto& coords =
                            session
                                ->normalized_coords;

                        const auto& alive =
                            session
                                ->alive_indices;

                        for (
                            std::size_t i =
                                begin;
                            i < end;
                            ++i
                        )
                        {
                            const auto index =
                                alive[i];

                            const auto z =
                                static_cast<
                                    std::int32_t
                                >(
                                    index
                                    / plane
                                );

                            const auto remainder =
                                index
                                % plane;

                            const auto y =
                                static_cast<
                                    std::int32_t
                                >(
                                    remainder
                                    / width
                                );

                            const auto x =
                                static_cast<
                                    std::int32_t
                                >(
                                    remainder
                                    % width
                                );

                            const float nx =
                                coords[
                                    static_cast<
                                        std::size_t
                                    >(x)
                                ];

                            const float ny =
                                coords[
                                    static_cast<
                                        std::size_t
                                    >(y)
                                ];

                            const float nz =
                                coords[
                                    static_cast<
                                        std::size_t
                                    >(z)
                                ];

                            if (
                                !sample_projection(
                                    compiled,
                                    nx,
                                    ny,
                                    nz
                                )
                            )
                            {
                                continue;
                            }

                            result
                                .alive_indices
                                .push_back(
                                    index
                                );

                            result
                                .bounds
                                .add(
                                    x,
                                    y,
                                    z
                                );
                        }

                        return result;
                    }
                )
            );
        }

        std::vector<
            std::uint32_t
        > next_alive;

        next_alive.reserve(
            alive_count
        );

        BoundsAccumulator next_bounds;

        for (auto& future : futures)
        {
            auto worker_result =
                future.get();

            next_bounds.merge(
                worker_result.bounds
            );

            next_alive.insert(
                next_alive.end(),
                std::make_move_iterator(
                    worker_result
                        .alive_indices
                        .begin()
                ),
                std::make_move_iterator(
                    worker_result
                        .alive_indices
                        .end()
                )
            );
        }

        std::fill(
            session->values.begin(),
            session->values.end(),
            0
        );

        for (
            const auto index :
            next_alive
        )
        {
            session->values[
                index
            ] = 1;
        }

        session->alive_indices =
            std::move(
                next_alive
            );

        session->bounds =
            next_bounds;

        if (
            out_surviving_voxels
            != nullptr
        )
        {
            *out_surviving_voxels =
                session
                    ->alive_indices
                    .size();
        }

        return BPT_OK;
    }
    catch (const std::bad_alloc&)
    {
        return BPT_ERROR_ALLOCATION_FAILED;
    }
    catch (...)
    {
        return BPT_ERROR_INTERNAL;
    }
}


BptResultCode
bpt_visual_hull_snapshot(
    const BptVisualHullSession* session,
    BptVolumeResult* out_volume
)
{
    if (
        session == nullptr
        || out_volume == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    try
    {
        *out_volume =
            BptVolumeResult {};

        out_volume->width =
            session->width;

        out_volume->depth =
            session->depth;

        out_volume->height =
            session->height;

        out_volume->value_count =
            session->values.size();

        out_volume->occupied_count =
            session
                ->alive_indices
                .size();

        if (
            !session
                ->values
                .empty()
        )
        {
            out_volume->values =
                new std::uint8_t[
                    session
                        ->values
                        .size()
                ];

            std::copy(
                session
                    ->values
                    .begin(),
                session
                    ->values
                    .end(),
                out_volume->values
            );
        }

        write_volume_bounds(
            session->bounds,
            out_volume
        );

        return BPT_OK;
    }
    catch (const std::bad_alloc&)
    {
        bpt_free_volume(
            out_volume
        );

        return BPT_ERROR_ALLOCATION_FAILED;
    }
    catch (...)
    {
        bpt_free_volume(
            out_volume
        );

        return BPT_ERROR_INTERNAL;
    }
}


void
bpt_visual_hull_destroy(
    BptVisualHullSession* session
)
{
    delete session;
}


BptResultCode
bpt_build_visual_hull(
    const BptProjectionInput* projections,
    const std::size_t projection_count,
    const BptScanOptions* options,
    BptVolumeResult* out_volume
)
{
    if (
        projections == nullptr
        || options == nullptr
        || out_volume == nullptr
    )
    {
        return BPT_ERROR_INVALID_ARGUMENT;
    }

    if (projection_count < 2)
    {
        return BPT_ERROR_NOT_ENOUGH_PROJECTIONS;
    }

    BptVisualHullSession* session =
        nullptr;

    auto result =
        bpt_visual_hull_create(
            options,
            &session
        );

    if (result != BPT_OK)
    {
        return result;
    }

    for (
        std::size_t index = 0;
        index < projection_count;
        ++index
    )
    {
        result =
            bpt_visual_hull_apply_projection(
                session,
                &projections[index],
                nullptr
            );

        if (result != BPT_OK)
        {
            bpt_visual_hull_destroy(
                session
            );

            return result;
        }
    }

    result =
        bpt_visual_hull_snapshot(
            session,
            out_volume
        );

    bpt_visual_hull_destroy(
        session
    );

    return result;
}


}