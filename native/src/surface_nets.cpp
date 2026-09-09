#include "bpt_core.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <new>
#include <vector>


namespace
{


// ---------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------

struct Vec3
{
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3& operator+=(
        const Vec3& other
    )
    {
        x += other.x;
        y += other.y;
        z += other.z;

        return *this;
    }
};


Vec3 operator+(
    const Vec3& a,
    const Vec3& b
)
{
    return Vec3 {
        a.x + b.x,
        a.y + b.y,
        a.z + b.z
    };
}


Vec3 operator*(
    const Vec3& value,
    const float factor
)
{
    return Vec3 {
        value.x * factor,
        value.y * factor,
        value.z * factor
    };
}


// ---------------------------------------------------------
// Surface Nets topology
// ---------------------------------------------------------

struct CornerOffset
{
    std::int32_t x;
    std::int32_t y;
    std::int32_t z;
};


struct EdgeCorners
{
    std::uint8_t a;
    std::uint8_t b;
};


constexpr CornerOffset kCorners[8] = {
    {0, 0, 0},
    {1, 0, 0},
    {1, 1, 0},
    {0, 1, 0},

    {0, 0, 1},
    {1, 0, 1},
    {1, 1, 1},
    {0, 1, 1},
};


constexpr EdgeCorners kEdges[12] = {
    {0, 1},
    {1, 2},
    {2, 3},
    {3, 0},

    {4, 5},
    {5, 6},
    {6, 7},
    {7, 4},

    {0, 4},
    {1, 5},
    {2, 6},
    {3, 7},
};


constexpr std::uint32_t kInvalidVertex =
    std::numeric_limits<
        std::uint32_t
    >::max();


// ---------------------------------------------------------
// Builder
// ---------------------------------------------------------

struct SurfaceNetsBuilder
{
    std::vector<float>
        vertices;

    std::vector<std::uint32_t>
        indices;

    std::vector<std::uint32_t>
        polygon_starts;

    std::vector<std::uint8_t>
        polygon_sizes;


    std::uint32_t add_vertex(
        const Vec3& point
    )
    {
        const auto index =
            static_cast<
                std::uint32_t
            >(
                vertices.size()
                / 3
            );

        vertices.push_back(
            point.x
        );

        vertices.push_back(
            point.y
        );

        vertices.push_back(
            point.z
        );

        return index;
    }


    void add_quad(
        const std::uint32_t a,
        const std::uint32_t b,
        const std::uint32_t c,
        const std::uint32_t d
    )
    {
        polygon_starts.push_back(
            static_cast<
                std::uint32_t
            >(
                indices.size()
            )
        );

        polygon_sizes.push_back(
            4
        );

        indices.push_back(a);
        indices.push_back(b);
        indices.push_back(c);
        indices.push_back(d);
    }
};


// ---------------------------------------------------------
// Padded binary field
// ---------------------------------------------------------
//
// The original volume stores occupied voxels.
//
// Surface Nets is easier to express as samples positioned
// at voxel centres.
//
// A one-sample empty border is added around the volume:
//
// padded sample 0
//     -> virtual empty sample at -0.5 voxel
//
// padded sample 1
//     -> original voxel 0 centre at +0.5 voxel
//
// ...
//
// padded sample width
//     -> original voxel width-1 centre
//
// padded sample width+1
//     -> virtual empty sample at width+0.5 voxel
//
// Therefore the midpoint between an occupied boundary
// sample and its virtual empty neighbour lies exactly on
// the historical voxel face.
// ---------------------------------------------------------

bool sample_occupied(
    const BptVolumeResult& volume,
    const std::int32_t px,
    const std::int32_t py,
    const std::int32_t pz
)
{
    if (
        px <= 0
        || py <= 0
        || pz <= 0
        || px > volume.width
        || py > volume.depth
        || pz > volume.height
    )
    {
        return false;
    }

    const auto x =
        static_cast<
            std::size_t
        >(
            px - 1
        );

    const auto y =
        static_cast<
            std::size_t
        >(
            py - 1
        );

    const auto z =
        static_cast<
            std::size_t
        >(
            pz - 1
        );

    const auto width =
        static_cast<
            std::size_t
        >(
            volume.width
        );

    const auto depth =
        static_cast<
            std::size_t
        >(
            volume.depth
        );

    const auto index =
        (
            z
            * depth
            + y
        )
        * width
        + x;

    return (
        volume.values[
            index
        ]
        != 0
    );
}


// ---------------------------------------------------------
// World coordinates
// ---------------------------------------------------------

Vec3 sample_world_position(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    const std::int32_t px,
    const std::int32_t py,
    const std::int32_t pz
)
{
    const float voxel_size =
        options.voxel_size;

    float offset_x =
        0.0f;

    float offset_y =
        0.0f;

    if (
        options.center_xy != 0
    )
    {
        /*
         * Exactly the same X/Y centering convention
         * as the historical block mesher.
         */
        offset_x =
            static_cast<float>(
                volume.width
            )
            * voxel_size
            * 0.5f;

        offset_y =
            static_cast<float>(
                volume.depth
            )
            * voxel_size
            * 0.5f;
    }

    return Vec3 {
        (
            static_cast<float>(
                px
            )
            - 0.5f
        )
        * voxel_size
        - offset_x,

        (
            static_cast<float>(
                py
            )
            - 0.5f
        )
        * voxel_size
        - offset_y,

        (
            static_cast<float>(
                pz
            )
            - 0.5f
        )
        * voxel_size,
    };
}


// ---------------------------------------------------------
// Active-cell grid
// ---------------------------------------------------------

struct CellGrid
{
    std::int32_t min_x = 0;
    std::int32_t min_y = 0;
    std::int32_t min_z = 0;

    std::int32_t max_x = -1;
    std::int32_t max_y = -1;
    std::int32_t max_z = -1;

    std::size_t size_x = 0;
    std::size_t size_y = 0;
    std::size_t size_z = 0;

    std::vector<std::uint32_t>
        vertices;


    bool contains(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        return (
            x >= min_x
            && x <= max_x
            && y >= min_y
            && y <= max_y
            && z >= min_z
            && z <= max_z
        );
    }


    std::size_t index(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        const auto local_x =
            static_cast<
                std::size_t
            >(
                x - min_x
            );

        const auto local_y =
            static_cast<
                std::size_t
            >(
                y - min_y
            );

        const auto local_z =
            static_cast<
                std::size_t
            >(
                z - min_z
            );

        return (
            (
                local_z
                * size_y
                + local_y
            )
            * size_x
            + local_x
        );
    }


    std::uint32_t get(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z
    ) const
    {
        if (
            !contains(
                x,
                y,
                z
            )
        )
        {
            return (
                kInvalidVertex
            );
        }

        return vertices[
            index(
                x,
                y,
                z
            )
        ];
    }


    void set(
        const std::int32_t x,
        const std::int32_t y,
        const std::int32_t z,
        const std::uint32_t vertex
    )
    {
        vertices[
            index(
                x,
                y,
                z
            )
        ] = vertex;
    }
};


CellGrid create_cell_grid(
    const BptVolumeResult& volume
)
{
    CellGrid grid;

    /*
     * An occupied sample at voxel x corresponds to
     * padded sample x+1.
     *
     * The boundary cells around it therefore span
     * cell coordinates x and x+1.
     */
    grid.min_x =
        std::clamp(
            volume.min_x,
            0,
            volume.width
        );

    grid.max_x =
        std::clamp(
            volume.max_x + 1,
            0,
            volume.width
        );

    grid.min_y =
        std::clamp(
            volume.min_y,
            0,
            volume.depth
        );

    grid.max_y =
        std::clamp(
            volume.max_y + 1,
            0,
            volume.depth
        );

    grid.min_z =
        std::clamp(
            volume.min_z,
            0,
            volume.height
        );

    grid.max_z =
        std::clamp(
            volume.max_z + 1,
            0,
            volume.height
        );

    if (
        grid.min_x > grid.max_x
        || grid.min_y > grid.max_y
        || grid.min_z > grid.max_z
    )
    {
        return grid;
    }

    grid.size_x =
        static_cast<
            std::size_t
        >(
            grid.max_x
            - grid.min_x
            + 1
        );

    grid.size_y =
        static_cast<
            std::size_t
        >(
            grid.max_y
            - grid.min_y
            + 1
        );

    grid.size_z =
        static_cast<
            std::size_t
        >(
            grid.max_z
            - grid.min_z
            + 1
        );

    const auto cell_count =
        grid.size_x
        * grid.size_y
        * grid.size_z;

    grid.vertices.assign(
        cell_count,
        kInvalidVertex
    );

    return grid;
}


// ---------------------------------------------------------
// Cell vertex
// ---------------------------------------------------------

bool build_cell_vertex(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    const std::int32_t cell_x,
    const std::int32_t cell_y,
    const std::int32_t cell_z,
    Vec3* out_position
)
{
    bool occupied[8];

    std::size_t occupied_count =
        0;

    for (
        std::size_t corner = 0;
        corner < 8;
        ++corner
    )
    {
        const auto& offset =
            kCorners[
                corner
            ];

        occupied[
            corner
        ] = sample_occupied(
            volume,
            cell_x + offset.x,
            cell_y + offset.y,
            cell_z + offset.z
        );

        if (
            occupied[
                corner
            ]
        )
        {
            ++occupied_count;
        }
    }

    /*
     * No sign change:
     *
     * entirely outside
     * or entirely inside.
     */
    if (
        occupied_count == 0
        || occupied_count == 8
    )
    {
        return false;
    }

    Vec3 sum;

    std::size_t crossings =
        0;

    for (
        const auto& edge :
        kEdges
    )
    {
        if (
            occupied[
                edge.a
            ]
            ==
            occupied[
                edge.b
            ]
        )
        {
            continue;
        }

        const auto& a_offset =
            kCorners[
                edge.a
            ];

        const auto& b_offset =
            kCorners[
                edge.b
            ];

        const auto a =
            sample_world_position(
                volume,
                options,
                cell_x + a_offset.x,
                cell_y + a_offset.y,
                cell_z + a_offset.z
            );

        const auto b =
            sample_world_position(
                volume,
                options,
                cell_x + b_offset.x,
                cell_y + b_offset.y,
                cell_z + b_offset.z
            );

        /*
         * Binary scalar field:
         *
         * inside  = +1
         * outside = -1
         *
         * The zero crossing therefore lies exactly
         * at the edge midpoint.
         */
        const auto midpoint =
            (
                a
                + b
            )
            * 0.5f;

        sum += midpoint;

        ++crossings;
    }

    if (
        crossings == 0
    )
    {
        return false;
    }

    const float inverse =
        1.0f
        / static_cast<float>(
            crossings
        );

    *out_position =
        sum
        * inverse;

    return true;
}


// ---------------------------------------------------------
// Generate all active-cell vertices
// ---------------------------------------------------------

void generate_cell_vertices(
    const BptVolumeResult& volume,
    const BptMeshOptions& options,
    CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    /*
     * Boundary cells are usually proportional to surface
     * area rather than volume, but reserving against the
     * occupied count gives a useful low-cost estimate.
     */
    builder.vertices.reserve(
        volume.occupied_count
        * 6
    );

    for (
        std::int32_t z = grid.min_z;
        z <= grid.max_z;
        ++z
    )
    {
        for (
            std::int32_t y = grid.min_y;
            y <= grid.max_y;
            ++y
        )
        {
            for (
                std::int32_t x = grid.min_x;
                x <= grid.max_x;
                ++x
            )
            {
                Vec3 position;

                if (
                    !build_cell_vertex(
                        volume,
                        options,
                        x,
                        y,
                        z,
                        &position
                    )
                )
                {
                    continue;
                }

                const auto vertex =
                    builder.add_vertex(
                        position
                    );

                grid.set(
                    x,
                    y,
                    z,
                    vertex
                );
            }
        }
    }
}


// ---------------------------------------------------------
// Quad helper
// ---------------------------------------------------------

bool valid_quad(
    const std::uint32_t a,
    const std::uint32_t b,
    const std::uint32_t c,
    const std::uint32_t d
)
{
    return (
        a != kInvalidVertex
        && b != kInvalidVertex
        && c != kInvalidVertex
        && d != kInvalidVertex
    );
}


void add_oriented_quad(
    SurfaceNetsBuilder& builder,
    const bool low_sample_inside,
    const std::uint32_t a,
    const std::uint32_t b,
    const std::uint32_t c,
    const std::uint32_t d
)
{
    if (
        low_sample_inside
    )
    {
        /*
         * Occupied -> empty while moving in the positive
         * axis direction.
         *
         * Outward normal therefore points +axis.
         */
        builder.add_quad(
            a,
            b,
            c,
            d
        );
    }
    else
    {
        /*
         * Empty -> occupied.
         *
         * Outward normal points -axis.
         */
        builder.add_quad(
            d,
            c,
            b,
            a
        );
    }
}


// ---------------------------------------------------------
// X-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_x_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y + 1;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z + 1;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px + 1,
                        py,
                        pz
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * Viewed from +X:
                 *
                 * a ---- b
                 * |      |
                 * d ---- c
                 *
                 * gives +X winding.
                 */
                const auto a =
                    grid.get(
                        px,
                        py - 1,
                        pz - 1
                    );

                const auto b =
                    grid.get(
                        px,
                        py,
                        pz - 1
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px,
                        py - 1,
                        pz
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}


// ---------------------------------------------------------
// Y-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_y_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x + 1;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z + 1;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px,
                        py + 1,
                        pz
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * +Y winding:
                 *
                 * lower X/lower Z
                 * -> lower X/upper Z
                 * -> upper X/upper Z
                 * -> upper X/lower Z
                 */
                const auto a =
                    grid.get(
                        px - 1,
                        py,
                        pz - 1
                    );

                const auto b =
                    grid.get(
                        px - 1,
                        py,
                        pz
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px,
                        py,
                        pz - 1
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}


// ---------------------------------------------------------
// Z-directed sign-changing edges
// ---------------------------------------------------------

BptResultCode generate_z_edge_quads(
    const BptVolumeResult& volume,
    const CellGrid& grid,
    SurfaceNetsBuilder& builder
)
{
    const auto min_x =
        volume.min_x + 1;

    const auto max_x =
        volume.max_x + 1;

    const auto min_y =
        volume.min_y + 1;

    const auto max_y =
        volume.max_y + 1;

    const auto min_z =
        volume.min_z;

    const auto max_z =
        volume.max_z + 1;

    for (
        std::int32_t pz = min_z;
        pz <= max_z;
        ++pz
    )
    {
        for (
            std::int32_t py = min_y;
            py <= max_y;
            ++py
        )
        {
            for (
                std::int32_t px = min_x;
                px <= max_x;
                ++px
            )
            {
                const bool low =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz
                    );

                const bool high =
                    sample_occupied(
                        volume,
                        px,
                        py,
                        pz + 1
                    );

                if (
                    low == high
                )
                {
                    continue;
                }

                /*
                 * +Z winding:
                 *
                 * lower X/lower Y
                 * -> upper X/lower Y
                 * -> upper X/upper Y
                 * -> lower X/upper Y
                 */
                const auto a =
                    grid.get(
                        px - 1,
                        py - 1,
                        pz
                    );

                const auto b =
                    grid.get(
                        px,
                        py - 1,
                        pz
                    );

                const auto c =
                    grid.get(
                        px,
                        py,
                        pz
                    );

                const auto d =
                    grid.get(
                        px - 1,
                        py,
                        pz
                    );

                if (
                    !valid_quad(
                        a,
                        b,
                        c,
                        d
                    )
                )
                {
                    return (
                        BPT_ERROR_INTERNAL
                    );
                }

                add_oriented_quad(
                    builder,
                    low,
                    a,
                    b,
                    c,
                    d
                );
            }
        }
    }

    return BPT_OK;
}


// ---------------------------------------------------------
// Result copy
// ---------------------------------------------------------

void copy_to_result(
    SurfaceNetsBuilder& builder,
    BptMeshResult* out_mesh
)
{
    *out_mesh =
        BptMeshResult {};

    out_mesh->vertex_float_count =
        builder.vertices.size();

    out_mesh->index_count =
        builder.indices.size();

    out_mesh->polygon_count =
        builder.polygon_sizes.size();

    if (
        !builder.vertices.empty()
    )
    {
        out_mesh->vertices =
            new float[
                builder.vertices.size()
            ];

        std::copy(
            builder.vertices.begin(),
            builder.vertices.end(),
            out_mesh->vertices
        );
    }

    if (
        !builder.indices.empty()
    )
    {
        out_mesh->indices =
            new std::uint32_t[
                builder.indices.size()
            ];

        std::copy(
            builder.indices.begin(),
            builder.indices.end(),
            out_mesh->indices
        );
    }

    if (
        !builder
            .polygon_starts
            .empty()
    )
    {
        out_mesh->polygon_starts =
            new std::uint32_t[
                builder
                    .polygon_starts
                    .size()
            ];

        std::copy(
            builder
                .polygon_starts
                .begin(),
            builder
                .polygon_starts
                .end(),
            out_mesh
                ->polygon_starts
        );
    }

    if (
        !builder
            .polygon_sizes
            .empty()
    )
    {
        out_mesh->polygon_sizes =
            new std::uint8_t[
                builder
                    .polygon_sizes
                    .size()
            ];

        std::copy(
            builder
                .polygon_sizes
                .begin(),
            builder
                .polygon_sizes
                .end(),
            out_mesh
                ->polygon_sizes
        );
    }
}


} // namespace


// ---------------------------------------------------------
// Internal entry point
// ---------------------------------------------------------

namespace bpt_internal
{


BptResultCode
build_surface_nets_mesh(
    const BptVolumeResult* volume,
    const BptMeshOptions* options,
    BptMeshResult* out_mesh
)
{
    if (
        volume == nullptr
        || options == nullptr
        || out_mesh == nullptr
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    /*
     * mesh.cpp already validates these inputs before
     * dispatching here, but retain the basic checks so
     * this backend stays safe if reused internally later.
     */
    if (
        options->voxel_size <= 0.0f
    )
    {
        return (
            BPT_ERROR_INVALID_ARGUMENT
        );
    }

    if (
        volume->occupied_count == 0
        || volume->has_bounds == 0
    )
    {
        *out_mesh =
            BptMeshResult {};

        return BPT_OK;
    }

    try
    {
        SurfaceNetsBuilder builder;

        /*
         * Rough reservation only.
         *
         * Surface Nets usually generates dramatically fewer
         * polygons than one face per exposed voxel side.
         */
        builder.indices.reserve(
            volume->occupied_count
            * 8
        );

        builder.polygon_starts.reserve(
            volume->occupied_count
            * 2
        );

        builder.polygon_sizes.reserve(
            volume->occupied_count
            * 2
        );

        auto grid =
            create_cell_grid(
                *volume
            );

        if (
            grid.vertices.empty()
        )
        {
            *out_mesh =
                BptMeshResult {};

            return BPT_OK;
        }

        // -------------------------------------------------
        // Pass 1
        //
        // One vertex per active boundary cell.
        // -------------------------------------------------

        generate_cell_vertices(
            *volume,
            *options,
            grid,
            builder
        );

        if (
            builder.vertices.empty()
        )
        {
            *out_mesh =
                BptMeshResult {};

            return BPT_OK;
        }

        // -------------------------------------------------
        // Pass 2
        //
        // Every sign-changing sample edge connects the
        // four surrounding active cells.
        // -------------------------------------------------

        auto result =
            generate_x_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        result =
            generate_y_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        result =
            generate_z_edge_quads(
                *volume,
                grid,
                builder
            );

        if (
            result != BPT_OK
        )
        {
            return result;
        }

        copy_to_result(
            builder,
            out_mesh
        );

        return BPT_OK;
    }
    catch (
        const std::bad_alloc&
    )
    {
        bpt_free_mesh(
            out_mesh
        );

        return (
            BPT_ERROR_ALLOCATION_FAILED
        );
    }
    catch (...)
    {
        bpt_free_mesh(
            out_mesh
        );

        return (
            BPT_ERROR_INTERNAL
        );
    }
}


} // namespace bpt_internal