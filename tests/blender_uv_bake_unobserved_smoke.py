"""Actual sampler/bake checks: inferred color must not become observed coverage."""
import importlib
from array import array
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
package=importlib.import_module(ROOT.name);package.register()
def module(name):return importlib.import_module(ROOT.name+'.'+name)

config_module=module('implementations.uv_bake.config')
sampler_module=module('implementations.uv_bake.sampler')
settings_module=module('implementations.uv_bake.settings')
contracts=module('core.geometry_contracts')
uv=module('core.uv_bake')
projected=module('core.projected_material')
image_buffer=module('core.projected_material.image_buffer')
config=config_module.UVBakeMaterialConfig(texture_size=1,padding_pixels=0,enable_visibility=False,
    unobserved_color=(.62,.44,.28))
config.validate()
assert config_module.UVBakeMaterialConfig().unobserved_color==projected.DEFAULT_FALLBACK_COLOR[:3]
for invalid in ((1,2,3),(0,0,float('nan')),(0,0),(0,0,0,1)):
    try:config_module.UVBakeMaterialConfig(unobserved_color=invalid).validate()
    except ValueError:pass
    else:raise AssertionError('Accepted invalid unobserved color')
assert settings_module._config_from_settings(SimpleNamespace(uv_bake_unobserved_color=[.62,.44,.28])).unobserved_color==(.62,.44,.28)
geometry=SimpleNamespace(projection_space=contracts.GeometryProjectionSpace(1,1,1))
triangle=uv.UVBakeTriangle(*[uv.UVBakeVertex(position=p,normal=(0,-1,0),uv=t) for p,t in (
    ((-.5,0,0),(0,0)),((.5,0,0),(1,0)),((0,0,1),(0,1)))])
for diagnostics in (False,True):
    sampler=sampler_module._build_surface_sampler(geometry,config,views=[],diagnostics=diagnostics)
    sample=sampler((0,0,.5),(0,-1,0))
    assert sample.color==(.62,.44,.28,1.) and sample.used_fallback and sample.selected_samples==0
    baked=uv.bake_uv_texture([triangle],sampler,config=config.to_bake_config())
    assert baked.stats.fallback_samples==baked.stats.surface_samples>0
    assert baked.stats.selected_source_samples==0
    if diagnostics:assert sampler.diagnostics['neutral_fallback_samples']>0
view=projected.ProjectedMaterialView.from_image_buffer(name='front',
    image_buffer=image_buffer.ImageBuffer(1,1,array('f',(.9,.2,.1,1.))),
    azimuth_degrees=0,elevation_degrees=0)
sampler=sampler_module._build_surface_sampler(geometry,config,views=[view],diagnostics=True)
sample=sampler((0,0,.5),(0,-1,0))
assert not sample.used_fallback and sample.selected_samples==1
assert all(abs(a-b)<1e-6 for a,b in zip(sample.color,(.9,.2,.1,1.)))
import bpy
assert len(bpy.context.scene.bpt_settings.uv_bake_unobserved_color)==3
print('UV_UNOBSERVED_COLOR: observed pixels preserved; inferred color still counted as fallback')
