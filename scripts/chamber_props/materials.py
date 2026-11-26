"""Deterministic painterly PBR plates, authored here without external image assets."""
import math
import bpy
import numpy as np


def noise(size, cells, seed):
    rng = np.random.default_rng(seed)
    grid = rng.random((cells + 1, cells + 1))
    pos = np.arange(size) * cells / size
    index = pos.astype(int)
    blend = pos - index
    blend = blend * blend * (3 - 2 * blend)
    a = grid[index[:, None], index[None, :]]
    b = grid[index[:, None] + 1, index[None, :]]
    c = grid[index[:, None], index[None, :] + 1]
    d = grid[index[:, None] + 1, index[None, :] + 1]
    return (a * (1-blend[:, None]) + b * blend[:, None]) * (1-blend[None, :]) + (c * (1-blend[:, None]) + d * blend[:, None]) * blend[None, :]


def create(folder, size=512):
    """Three opaque standard metallic/roughness materials; no shader dependency."""
    folder.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:size, 0:size] / size
    broad = noise(size, 9, 38)
    brush = noise(size, 34, 40)
    grain = noise(size, 100, 41)
    # Angular painted mineral patches. Their boundaries carry restrained cracks,
    # while the interiors stay broad enough to read at actual game scale.
    rng = np.random.default_rng(830)
    sites = rng.random((28, 2))
    distances = np.stack([(x-px)**2+(y-py)**2 for px,py in sites])
    nearest = np.argmin(distances, axis=0)
    ordered = np.partition(distances, 1, axis=0)
    facet = rng.random(28)[nearest]
    vein = np.maximum(0, 1-(ordered[1]-ordered[0])/.0014)
    plates = {}
    for name, base, metallic, roughness in (
        ('ChamberStone', (0.322, 0.396, 0.392), 0.0, 0.86),
        ('DarkTimber', (0.235, 0.255, 0.219), 0.0, 0.9),
        ('AgedBronze', (0.553, 0.482, 0.310), 0.35, 0.76),
    ):
        if name == 'ChamberStone':
            # Broad slanted mineral strata, restrained painted chips, not baked lighting.
            strata = np.sin((x * 7 + y * 11 + broad * 1.6) * math.tau)
            shade = 0.73 + broad * 0.21 + facet * .22 + brush * .035 + strata * 0.035 - vein * .10
            flecks = np.maximum(0, brush - 0.74) * 0.025
        elif name == 'DarkTimber':
            lines = np.sin((x * 31 + noise(size, 5, 7) * 1.3) * math.tau)
            shade = 0.8 + broad * 0.32 + lines * 0.035 + grain * 0.015
            flecks = np.zeros_like(shade)
        else:
            shade = 0.72 + broad * 0.33 + brush * 0.055 + grain * 0.012
            flecks = np.maximum(0, brush - 0.62) * 0.06
        pixels = np.ones((size, size, 4), dtype=np.float32)
        pixels[:, :, :3] = np.clip(np.array(base)[None, None, :] * shade[:, :, None] + flecks[:, :, None], 0, 1)
        image = bpy.data.images.new(name + '-paint', width=size, height=size)
        image.colorspace_settings.name = 'sRGB'
        image.pixels.foreach_set(pixels.ravel())
        image.filepath_raw = str(folder / (name + '-basecolor.png'))
        image.file_format = 'PNG'
        image.save()
        image.pack()
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        p = mat.node_tree.nodes.get('Principled BSDF')
        texture = mat.node_tree.nodes.new('ShaderNodeTexImage')
        texture.image = image
        mat.node_tree.links.new(texture.outputs['Color'], p.inputs['Base Color'])
        p.inputs['Metallic'].default_value = metallic
        p.inputs['Roughness'].default_value = roughness
        mat.diffuse_color = (*base, 1)
        plates[name] = mat
    return plates
