#include "bpt_core.h"

#include <cstddef>
#include <cstdint>


extern "C"
{


void
bpt_free_volume(
    BptVolumeResult* volume
)
{
    if (volume == nullptr)
    {
        return;
    }

    delete[] volume->values;

    *volume =
        BptVolumeResult {};
}


void
bpt_free_mesh(
    BptMeshResult* mesh
)
{
    if (mesh == nullptr)
    {
        return;
    }

    delete[] mesh->vertices;
    delete[] mesh->indices;
    delete[] mesh->polygon_starts;
    delete[] mesh->polygon_sizes;

    *mesh =
        BptMeshResult {};
}


const char*
bpt_result_message(
    const BptResultCode code
)
{
    switch (code)
    {
        case BPT_OK:
            return "OK";

        case BPT_ERROR_INVALID_ARGUMENT:
            return "Invalid argument";

        case BPT_ERROR_INVALID_RESOLUTION:
            return "Invalid resolution";

        case BPT_ERROR_NOT_ENOUGH_PROJECTIONS:
            return "At least two projections are required";

        case BPT_ERROR_ALLOCATION_FAILED:
            return "Memory allocation failed";

        case BPT_ERROR_INTERNAL:
            return "Internal native error";

        default:
            return "Unknown result code";
    }
}


std::uint32_t
bpt_abi_version()
{
    return 1u;
}


}