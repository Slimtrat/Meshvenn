#include "bpt_core.h"

#include <algorithm>
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


constexpr float kEpsilon =
    1e-9f;


/*
 * Do not spawn a large number of worker threads
 * once only a small number of voxels remain.
 */
constexpr std::size_t
    kMinVoxelsPerWorker =
        32768;


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


float radians(
    const float degrees
)
{
    constexpr float kPi =
        3.14159265358979323846f;

    return (
        degrees
        * kPi
        / 180.0f
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


BptResultCode validate_projection(
    const BptProjectionInput* projection
)
{
    if (projection == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (projection->mask == nullptr)
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        projection->width <= 0
        || projection->height <= 0
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
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

    const float cos_az =
        std::cos(
            azimuth
        );

    const float sin_az =
        std::sin(
            azimuth
        );

    const float cos_el =
        std::cos(
            elevation
        );

    const float sin_el =
        std::sin(
            elevation
        );

    const float horizontal_extent =
        std::max(
            std::abs(
                cos_az
            )
            + std::abs(
                sin_az
            ),
            kEpsilon
        );

    const float vertical_extent =
        std::max(
            (
                horizontal_extent
                * std::abs(
                    sin_el
                )
            )
            + std::abs(
                cos_el
            ),
            kEpsilon
        );

    CompiledProjection result;

    result.mask =
        projection.mask;

    result.width =
        projection.width;

    result.height =
        projection.height;

    result.width_minus_one =
        static_cast<float>(
            projection.width - 1
        );

    result.height_minus_one =
        static_cast<float>(
            projection.height - 1
        );

    /*
     * Same convention as the previous
     * implementation: rotate the volume by
     * the inverse camera transform.
     */
    result.cos_az =
        cos_az;

    result.sin_az =
        -sin_az;

    result.cos_el =
        cos_el;

    result.sin_el =
        -sin_el;

    result.horizontal_extent =
        horizontal_extent;

    result.vertical_extent =
        vertical_extent;

    result.flip_x =
        projection.flip_x != 0;

    return result;
}


inline bool sample_projection(
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
            (
                x1
                / projection.horizontal_extent
            )
            + 1.0f
        )
        * 0.5f;

    const float v =
        (
            (
                z2
                / projection.vertical_extent
            )
            + 1.0f
        )
        * 0.5f;

    if (projection.flip_x)
    {
        u =
            1.0f
            - u;
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
        std::clamp(
            static_cast<
                std::int32_t
            >(
                u
                * projection.width_minus_one
                + 0.5f
            ),
            0,
            projection.width - 1
        );

    const auto y =
        std::clamp(
            static_cast<
                std::int32_t
            >(
                v
                * projection.height_minus_one
                + 0.5f
            ),
            0,
            projection.height - 1
        );

    const auto index =
        static_cast<
            std::size_t
        >(
            y
        )
        * static_cast<
            std::size_t
        >(
            projection.width
        )
        + static_cast<
            std::size_t
        >(
            x
        );

    return (
        projection.mask[index]
        != 0
    );
}


inline bool survives_projection(
    const CompiledProjection& projection,
    const float nx,
    const float ny,
    const float nz,
    const bool symmetry_x
)
{
    if (
        !sample_projection(
            projection,
            nx,
            ny,
            nz
        )
    )
    {
        return false;
    }

    if (!symmetry_x)
    {
        return true;
    }

    /*
     * Conservative X symmetry:
     *
     * a voxel survives only when both it and
     * its mirrored X position satisfy the
     * silhouette.
     *
     * Therefore x and -x always receive the
     * same result and the volume stays
     * symmetrical without creating geometry
     * outside the source silhouettes.
     */
    return sample_projection(
        projection,
        -nx,
        ny,
        nz
    );
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


} // namespace


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

    BoundsAccumulator bounds;

    std::int32_t thread_limit = 1;
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
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    *out_session =
        nullptr;

    const auto validation =
        validate_options(
            options
        );

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

        session->thread_limit =
            resolve_thread_count(
                options->thread_count
            );

        const auto resolution =
            static_cast<
                std::size_t
            >(
                options->resolution
            );

        const auto voxel_count =
            resolution
            * resolution
            * resolution;

        session
            ->alive_indices
            .resize(
                voxel_count
            );

        for (
            std::size_t index = 0;
            index < voxel_count;
            ++index
        )
        {
            session
                ->alive_indices[
                    index
                ] =
                    static_cast<
                        std::uint32_t
                    >(
                        index
                    );
        }

        session
            ->normalized_coords
            .resize(
                resolution
            );

        for (
            std::int32_t index = 0;
            index < options->resolution;
            ++index
        )
        {
            session
                ->normalized_coords[
                    static_cast<
                        std::size_t
                    >(
                        index
                    )
                ] =
                    grid_to_normalized(
                        index,
                        options->resolution
                    );
        }

        session->bounds.found =
            true;

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
    catch (
        const std::bad_alloc&
    )
    {
        return (
            BPT_ERROR_ALLOCATION_FAILED
        );
    }
    catch (...)
    {
        return (
            BPT_ERROR_INTERNAL
        );
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
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    const auto validation =
        validate_projection(
            projection
        );

    if (validation != BPT_OK)
    {
        return validation;
    }

    try
    {
        auto& alive =
            session->alive_indices;

        if (alive.empty())
        {
            session->bounds =
                BoundsAccumulator {};

            if (
                out_surviving_voxels
                != nullptr
            )
            {
                *out_surviving_voxels =
                    0;
            }

            return BPT_OK;
        }

        const auto compiled =
            compile_projection(
                *projection
            );

        const std::size_t alive_count =
            alive.size();

        const std::size_t worker_count =
            resolve_worker_count(
                alive_count,
                session->thread_limit
            );

        const std::size_t chunk_size =
            (
                alive_count
                + worker_count
                - 1
            )
            / worker_count;

        const auto width =
            static_cast<
                std::uint32_t
            >(
                session->width
            );

        const auto depth =
            static_cast<
                std::uint32_t
            >(
                session->depth
            );

        const auto plane =
            width
            * depth;

        const auto& coords =
            session->normalized_coords;

        const bool symmetry_x =
            session
                ->options
                .symmetry_x
            != 0;


        /*
         * Small workloads stay on the current
         * thread. This avoids std::async
         * overhead after the hull has already
         * become sparse.
         */
        if (worker_count == 1)
        {
            std::size_t write = 0;

            BoundsAccumulator next_bounds;

            for (
                std::size_t i = 0;
                i < alive_count;
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
                        >(
                            x
                        )
                    ];

                const float ny =
                    coords[
                        static_cast<
                            std::size_t
                        >(
                            y
                        )
                    ];

                const float nz =
                    coords[
                        static_cast<
                            std::size_t
                        >(
                            z
                        )
                    ];

                if (
                    !survives_projection(
                        compiled,
                        nx,
                        ny,
                        nz,
                        symmetry_x
                    )
                )
                {
                    continue;
                }

                alive[
                    write
                ] =
                    index;

                ++write;

                next_bounds.add(
                    x,
                    y,
                    z
                );
            }

            alive.resize(
                write
            );

            session->bounds =
                next_bounds;
        }
        else
        {
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
                    worker
                    * chunk_size;

                const auto end =
                    std::min(
                        begin
                        + chunk_size,
                        alive_count
                    );

                if (begin >= end)
                {
                    break;
                }

                futures.emplace_back(
                    std::async(
                        std::launch::async,
                        [
                            &alive,
                            &coords,
                            compiled,
                            symmetry_x,
                            begin,
                            end,
                            width,
                            plane
                        ]()
                        {
                            WorkerResult result;

                            result.begin =
                                begin;

                            std::size_t write =
                                begin;

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
                                        >(
                                            x
                                        )
                                    ];

                                const float ny =
                                    coords[
                                        static_cast<
                                            std::size_t
                                        >(
                                            y
                                        )
                                    ];

                                const float nz =
                                    coords[
                                        static_cast<
                                            std::size_t
                                        >(
                                            z
                                        )
                                    ];

                                if (
                                    !survives_projection(
                                        compiled,
                                        nx,
                                        ny,
                                        nz,
                                        symmetry_x
                                    )
                                )
                                {
                                    continue;
                                }

                                /*
                                 * Each worker only writes
                                 * inside its own source
                                 * range, so no synchronization
                                 * is required.
                                 */
                                alive[
                                    write
                                ] =
                                    index;

                                ++write;

                                result.bounds.add(
                                    x,
                                    y,
                                    z
                                );
                            }

                            result.survivor_count =
                                write
                                - begin;

                            return result;
                        }
                    )
                );
            }

            std::vector<
                WorkerResult
            > results;

            results.reserve(
                futures.size()
            );

            BoundsAccumulator next_bounds;

            for (
                auto& future :
                futures
            )
            {
                auto result =
                    future.get();

                next_bounds.merge(
                    result.bounds
                );

                results.push_back(
                    result
                );
            }

            /*
             * Workers compacted their own
             * independent ranges.
             *
             * Now pack those surviving ranges
             * together at the beginning of the
             * same vector.
             *
             * No second survivor vector and no
             * resolution^3 fill are required.
             */
            std::size_t write = 0;

            for (
                const auto& result :
                results
            )
            {
                if (
                    result.survivor_count
                    == 0
                )
                {
                    continue;
                }

                if (
                    write
                    != result.begin
                )
                {
                    std::move(
                        alive.begin()
                            + static_cast<
                                std::ptrdiff_t
                            >(
                                result.begin
                            ),
                        alive.begin()
                            + static_cast<
                                std::ptrdiff_t
                            >(
                                result.begin
                                + result
                                    .survivor_count
                            ),
                        alive.begin()
                            + static_cast<
                                std::ptrdiff_t
                            >(
                                write
                            )
                    );
                }

                write +=
                    result
                        .survivor_count;
            }

            alive.resize(
                write
            );

            session->bounds =
                next_bounds;
        }

        if (
            out_surviving_voxels
            != nullptr
        )
        {
            *out_surviving_voxels =
                alive.size();
        }

        return BPT_OK;
    }
    catch (
        const std::bad_alloc&
    )
    {
        return (
            BPT_ERROR_ALLOCATION_FAILED
        );
    }
    catch (...)
    {
        return (
            BPT_ERROR_INTERNAL
        );
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
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
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

        const auto width =
            static_cast<
                std::size_t
            >(
                session->width
            );

        const auto depth =
            static_cast<
                std::size_t
            >(
                session->depth
            );

        const auto height =
            static_cast<
                std::size_t
            >(
                session->height
            );

        const auto voxel_count =
            width
            * depth
            * height;

        out_volume->value_count =
            voxel_count;

        out_volume->occupied_count =
            session
                ->alive_indices
                .size();

        if (voxel_count > 0)
        {
            /*
             * Dense representation is created
             * only when somebody explicitly
             * requests a snapshot.
             */
            out_volume->values =
                new std::uint8_t[
                    voxel_count
                ]();

            for (
                const auto index :
                session->alive_indices
            )
            {
                out_volume->values[
                    index
                ] = 1;
            }
        }

        write_volume_bounds(
            session->bounds,
            out_volume
        );

        return BPT_OK;
    }
    catch (
        const std::bad_alloc&
    )
    {
        bpt_free_volume(
            out_volume
        );

        return (
            BPT_ERROR_ALLOCATION_FAILED
        );
    }
    catch (...)
    {
        bpt_free_volume(
            out_volume
        );

        return (
            BPT_ERROR_INTERNAL
        );
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
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (projection_count < 2)
    {
        return (
            BPT_ERROR_NOT_ENOUGH_PROJECTIONS
        );
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
                &projections[
                    index
                ],
                nullptr
            );

        if (result != BPT_OK)
        {
            bpt_visual_hull_destroy(
                session
            );

            return result;
        }

        /*
         * No point evaluating further views
         * after the hull became empty.
         */
        if (
            session
                ->alive_indices
                .empty()
        )
        {
            break;
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


} // extern "C"