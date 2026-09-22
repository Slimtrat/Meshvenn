#include "test_visual_hull_cases.h"
#include "test_visual_hull_support.h"
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <vector>

namespace visual_hull_test
{

void
test_mesh_generation()
{
    constexpr std::int32_t size =
        16;

    auto mask =
        center_mask(
            size
        );

    const BptProjectionInput projections[] = {
        projection(
            mask,
            size,
            0.0f
        ),
        projection(
            mask,
            size,
            90.0f
        ),
    };

    auto options =
        default_options(
            16
        );

    BptVolumeResult volume {};

    assert(
        bpt_build_visual_hull(
            projections,
            2,
            &options,
            &volume
        )
        == BPT_OK
    );

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            1,
            &mesh
        )
        == BPT_OK
    );

    assert(
        mesh.vertex_float_count
        > 0
    );

    assert(
        mesh.vertex_float_count
        % 3
        == 0
    );

    assert(
        mesh.index_count
        > 0
    );

    assert(
        mesh.index_count
        % 4
        == 0
    );

    assert(
        mesh.polygon_count
        > 0
    );

    assert(
        mesh.index_count
        == mesh.polygon_count
        * 4
    );

    for (
        std::size_t polygon = 0;
        polygon < mesh.polygon_count;
        ++polygon
    )
    {
        assert(
            mesh.polygon_sizes[
                polygon
            ]
            == 4
        );

        assert(
            mesh.polygon_starts[
                polygon
            ]
            == polygon * 4
        );
    }

    bpt_free_mesh(
        &mesh
    );

    bpt_free_volume(
        &volume
    );
}


void
test_empty_mesh_generation()
{
    constexpr std::int32_t size =
        8;

    std::vector<std::uint8_t> values(
        size * size * size,
        0
    );

    BptVolumeResult volume {};

    volume.width =
        size;

    volume.depth =
        size;

    volume.height =
        size;

    volume.values =
        values.data();

    volume.value_count =
        values.size();

    volume.occupied_count =
        0;

    volume.has_bounds =
        0;

    BptMeshResult mesh {};

    assert(
        bpt_build_surface_mesh(
            &volume,
            1.0f,
            1,
            &mesh
        )
        == BPT_OK
    );

    assert(
        mesh.vertex_float_count
        == 0
    );

    assert(
        mesh.index_count
        == 0
    );

    assert(
        mesh.polygon_count
        == 0
    );

    bpt_free_mesh(
        &mesh
    );
}



} // namespace visual_hull_test
