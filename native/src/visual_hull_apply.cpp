#include "visual_hull_projection.h"

#include <algorithm>
#include <future>
#include <new>
#include <utility>

using namespace bpt_visual_hull_detail;

extern "C"
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
