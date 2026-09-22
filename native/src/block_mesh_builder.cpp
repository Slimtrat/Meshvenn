#include "block_mesh_builder.h"

#include <algorithm>

namespace bpt_internal
{

// ---------------------------------------------------------
// Result copy
// ---------------------------------------------------------

void copy_to_result(
    MeshBuilder& builder,
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

    if (!builder.vertices.empty())
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

    if (!builder.indices.empty())
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

} // namespace bpt_internal
