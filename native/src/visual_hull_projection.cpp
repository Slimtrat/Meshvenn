#include "visual_hull_internal.h"

#include <algorithm>
#include <cmath>

namespace
{


constexpr float kEpsilon =
    1e-9f;


} // namespace

namespace bpt_visual_hull_detail
{

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

} // namespace bpt_visual_hull_detail
