#pragma once

#include <cstddef>
#include <cstdint>


#if defined(_WIN32)

    #if defined(BPT_CORE_BUILD)
        #define BPT_API __declspec(dllexport)
    #else
        #define BPT_API __declspec(dllimport)
    #endif

#else

    #define BPT_API __attribute__((visibility("default")))

#endif


extern "C"
{


// ---------------------------------------------------------
// Result codes
// ---------------------------------------------------------

enum BptResultCode : std::int32_t
{
    BPT_OK = 0,

    BPT_ERROR_INVALID_ARGUMENT = 1,
    BPT_ERROR_INVALID_RESOLUTION = 2,
    BPT_ERROR_NOT_ENOUGH_PROJECTIONS = 3,
    BPT_ERROR_ALLOCATION_FAILED = 4,
    BPT_ERROR_INTERNAL = 5,
};


// ---------------------------------------------------------
// Projection input
// ---------------------------------------------------------

struct BptProjectionInput
{
    // Binary mask.
    //
    // Expected layout:
    // row-major
    // width * height bytes
    //
    // 0 = background
    // non-zero = silhouette
    const std::uint8_t* mask;

    std::int32_t width;
    std::int32_t height;

    float azimuth_degrees;
    float elevation_degrees;

    // 0 = normal
    // non-zero = horizontally flipped
    std::uint8_t flip_x;

    // Reserved for future ABI extensions.
    std::uint8_t reserved_0;
    std::uint8_t reserved_1;
    std::uint8_t reserved_2;
};


// ---------------------------------------------------------
// Scan options
// ---------------------------------------------------------

struct BptScanOptions
{
    // Voxel grid:
    // resolution³
    std::int32_t resolution;

    // 0 = disabled
    // non-zero = enforce X symmetry on snapshots
    std::uint8_t symmetry_x;

    std::uint8_t reserved_0;
    std::uint8_t reserved_1;
    std::uint8_t reserved_2;

    // 0 means auto-detect.
    std::int32_t thread_count;
};


// ---------------------------------------------------------
// Volume result
// ---------------------------------------------------------

struct BptVolumeResult
{
    std::int32_t width;
    std::int32_t depth;
    std::int32_t height;

    // Dense byte buffer:
    // width * depth * height
    //
    // 0 = empty
    // non-zero = occupied
    std::uint8_t* values;

    std::size_t value_count;
    std::size_t occupied_count;

    // Inclusive occupied bounds.
    //
    // has_bounds == 0 means volume is empty.
    std::uint8_t has_bounds;

    std::uint8_t reserved_0;
    std::uint8_t reserved_1;
    std::uint8_t reserved_2;

    std::int32_t min_x;
    std::int32_t max_x;

    std::int32_t min_y;
    std::int32_t max_y;

    std::int32_t min_z;
    std::int32_t max_z;
};


// ---------------------------------------------------------
// Mesh result
// ---------------------------------------------------------

struct BptMeshResult
{
    // Flat xyz float array:
    //
    // [x0, y0, z0, x1, y1, z1, ...]
    float* vertices;

    std::size_t vertex_float_count;

    // Flat polygon vertex indices.
    //
    // V1 currently generates quads only.
    std::uint32_t* indices;

    std::size_t index_count;

    // Start index in `indices` for every polygon.
    std::uint32_t* polygon_starts;

    // Number of corners for every polygon.
    // V1 normally contains 4.
    std::uint8_t* polygon_sizes;

    std::size_t polygon_count;
};


// ---------------------------------------------------------
// Incremental scan session
// ---------------------------------------------------------

struct BptVisualHullSession;


// Creates an incremental visual hull session.
//
// The session initially contains a fully occupied resolution³ cube.
BPT_API
BptResultCode
bpt_visual_hull_create(
    const BptScanOptions* options,
    BptVisualHullSession** out_session
);


// Applies one silhouette projection.
//
// `out_surviving_voxels` may be null.
BPT_API
BptResultCode
bpt_visual_hull_apply_projection(
    BptVisualHullSession* session,
    const BptProjectionInput* projection,
    std::size_t* out_surviving_voxels
);


// Creates an independent copy of the current volume.
//
// This is intended for:
//
// 000 + 090
//     -> snapshot L2
//
// + 180 + 270
//     -> snapshot L4
//
// etc.
BPT_API
BptResultCode
bpt_visual_hull_snapshot(
    const BptVisualHullSession* session,
    BptVolumeResult* out_volume
);


// Releases a visual hull session.
BPT_API
void
bpt_visual_hull_destroy(
    BptVisualHullSession* session
);


// ---------------------------------------------------------
// One-shot visual hull
// ---------------------------------------------------------

// Convenience API.
//
// Equivalent to:
//
// create
// -> apply projection 0
// -> ...
// -> apply projection N
// -> snapshot
// -> destroy
BPT_API
BptResultCode
bpt_build_visual_hull(
    const BptProjectionInput* projections,
    std::size_t projection_count,
    const BptScanOptions* options,
    BptVolumeResult* out_volume
);


// ---------------------------------------------------------
// Mesh generation
// ---------------------------------------------------------

BPT_API
BptResultCode
bpt_build_surface_mesh(
    const BptVolumeResult* volume,
    float voxel_size,
    std::uint8_t center_xy,
    BptMeshResult* out_mesh
);


// ---------------------------------------------------------
// Memory management
// ---------------------------------------------------------

BPT_API
void
bpt_free_volume(
    BptVolumeResult* volume
);


BPT_API
void
bpt_free_mesh(
    BptMeshResult* mesh
);


// ---------------------------------------------------------
// Diagnostics
// ---------------------------------------------------------

BPT_API
const char*
bpt_result_message(
    BptResultCode code
);


// ABI version.
//
// Increment if one of the public structs/functions becomes
// binary incompatible.
BPT_API
std::uint32_t
bpt_abi_version();


}