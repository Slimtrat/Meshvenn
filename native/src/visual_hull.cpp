#include "visual_hull_internal.h"

#include <memory>
#include <new>

using namespace bpt_visual_hull_detail;

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
