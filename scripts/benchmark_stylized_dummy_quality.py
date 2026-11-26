"""Rebake and refit a pinned generated-view source without rebuilding its mesh.

Run in Blender. Input files are explicit and cached; no image generation runs.
The four outputs separate the effect of texture selection and arm fitting.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import statistics
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent))


def module(name):
    return importlib.import_module(f'{ROOT.name}.{name}')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def snapshot(mesh,rig):
    return dict(vertices=[list(v.co) for v in mesh.data.vertices],
        polygons=[list(p.vertices) for p in mesh.data.polygons],
        uvs=[list(x.uv) for x in mesh.data.uv_layers.active.data],
        bones=[dict(name=b.name,parent=b.parent.name if b.parent else None,
                    head=list(b.head_local),tail=list(b.tail_local)) for b in rig.data.bones],
        weights=[{mesh.vertex_groups[g.group].name:g.weight for g in v.groups} for v in mesh.data.vertices])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-blend',type=Path,required=True)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cardinal-priority',action='store_true',
        help='Prefer the first-sheet cardinal views and use their measured cloth median for unobserved samples')
    parser.add_argument('--variants',nargs='+',choices=('baseline','detail','trajectory','combined'),
        default=('baseline','detail','trajectory','combined'))
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if sha(args.source_blend)!=args.source_sha256:
        raise ValueError('Source Blender SHA256 changed')
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    data=json.loads(args.dataset.read_text(encoding='utf-8'))
    by_id={v['id']:v for v in data['views']}
    if len(data['eight_views'])!=8 or len(by_id)!=8:
        raise ValueError('Require the complete declared eight-view dataset')
    importlib.import_module(ROOT.name).register()
    pipeline=module('core.pipeline_contracts')
    contracts=module('core.geometry_contracts')
    rig_contracts=module('core.rig_contracts')
    report=dict(schema_version=1,source_blend_sha256=args.source_sha256,
        dataset_sha256=sha(args.dataset),ground_truth_3d=None,quality_certification='unknown',
        consumer_acceptance='unknown',cases=[])
    for name,rebake,refit in (('baseline',False,False),('detail',True,False),
                             ('trajectory',False,True),('combined',True,True)):
        if name not in args.variants:continue
        bpy.ops.wm.open_mainfile(filepath=str(args.source_blend.resolve()))
        mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH')
        rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        before=snapshot(mesh,rig)
        views=[]
        for identifier in data['eight_views']:
            view=by_id[identifier];path=args.dataset.parent/view['path']
            if sha(path)!=view['sha256']:raise ValueError('Source image changed: '+identifier)
            angle=view['azimuth_degrees']
            weight=(16. if angle%180==0 else 4. if angle%90==0 else 1.) if args.cardinal_priority and rebake else 1.
            views.append(SimpleNamespace(name=identifier,image=bpy.data.images.load(str(path)),enabled=True,
                azimuth=math.radians(angle),elevation=0.,flip_x=False,weight=weight))
        settings=SimpleNamespace(projections=views,alpha_threshold=.5,
            uv_bake_texture_size=512,uv_bake_samples_per_axis=1,uv_bake_padding_pixels=4,
            uv_bake_reuse_existing_uv=True,material_max_contributors=1)
        context=pipeline.PipelineContext(scene=bpy.context.scene,settings=settings)
        prepared=module('implementations.projection_images').ProjectionImagesImplementation().execute(context)
        if not prepared.success:raise RuntimeError(prepared.message)
        context.set_output(pipeline.PipelineStage.INPUT,prepared.payload)
        fallback=None
        if args.cardinal_priority and rebake:
            front=next(v for v in prepared.payload.material_views if v.name=='az000')
            pixels=[front.image.sample_bilinear_alpha_aware(.4+x*.01,.4+y*.01) for x in range(21) for y in range(31)]
            pixels=[c for c in pixels if c[3]>.9]
            if not pixels:raise ValueError('No opaque cloth observations in the declared front torso window')
            fallback=tuple(statistics.median(c[i] for c in pixels) for i in range(3))
            settings.uv_bake_unobserved_color=fallback
        if mesh.get('meshvenn_projection_convention')!='surface-envelope-v1':
            raise ValueError('Require the saved native projection frame, not inferred mesh bounds')
        space=contracts.GeometryProjectionSpace(
            width=mesh['meshvenn_projection_width'],depth=mesh['meshvenn_projection_depth'],
            height=mesh['meshvenn_projection_height'],voxel_size=mesh['meshvenn_projection_voxel_size'],
            center_xy=mesh['meshvenn_projection_center_xy'])
        geometry=contracts.GeometrySurfaceOutput(blender_object=mesh,source=prepared.payload,
            projection_space=space,
            implementation_id='native-visual-hull',metadata={'source_blend_sha256':args.source_sha256})
        context.set_output(pipeline.PipelineStage.GEOMETRY,geometry)
        row=dict(id=name,rebake=rebake,refit=refit)
        if rebake:
            outcome=module('implementations.uv_bake').UVBakeImplementation().execute(context)
            if not outcome.success:raise RuntimeError(outcome.message)
            context.set_output(pipeline.PipelineStage.MATERIAL,outcome.payload)
            row['material_metrics']=outcome.metrics
            row['material_policy']='single best geometrically scored visible source; same UVs and texture resolution'
            row['view_weights']={v.name:v.weight for v in views}
            if fallback is not None:
                row['unobserved_color_provenance']=dict(color=list(fallback),linear_rgb=True,
                    source='az000',uv_window=[.4,.4,.6,.7],opaque_samples=len(pixels),
                    method='per-channel median; inferred fill, not observed texture or coverage')
        if refit:
            # This is a new source rig, never a migration of an animated consumer.
            world=mesh.matrix_world.copy();mesh.parent=None;mesh.matrix_world=world
            for modifier in list(mesh.modifiers):
                if modifier.type!='ARMATURE':raise ValueError('Unexpected source modifier')
                mesh.modifiers.remove(modifier)
            native_names={b.name for b in rig.data.bones}
            if any(g.name not in native_names for g in mesh.vertex_groups):
                raise ValueError('Keep authored auxiliary groups outside this fitting benchmark')
            mesh.vertex_groups.clear()
            bpy.data.objects.remove(rig,do_unlink=True)
            outcome=module('implementations.canonical_rig_v2').CanonicalRigV2Implementation().execute(context)
            if not outcome.success:raise RuntimeError(outcome.message)
            context.set_output(pipeline.PipelineStage.RIG,outcome.payload)
            rig=outcome.payload.armature_object
            row['rig_fit']=outcome.metadata['rig_fit']
        else:
            context.set_output(pipeline.PipelineStage.RIG,rig_contracts.RigOutput(
                geometry=geometry,blender_object=mesh,armature_object=rig,
                implementation_id='canonical-biped-v2',semantic_bones={b.name:b.name for b in rig.data.bones},
                binding_method='preserved-pinned-source'))
        after=snapshot(mesh,rig)
        for key in ('vertices','polygons','uvs'):
            if before[key]!=after[key]:raise ValueError('Visual correction changed source '+key)
        if not refit and (before['bones']!=after['bones'] or before['weights']!=after['weights']):
            raise ValueError('Texture-only variant changed rig or weights')
        row['source_vertices_polygons_uvs_exact']=True
        row['rig_preserved_exact']=not refit
        out=args.output/name;out.mkdir()
        target=out/'character.glb'
        context.metadata.update(export_output_path=str(target),export_overwrite_existing=False,export_validate_roundtrip=True)
        exported=module('implementations.glb_export').GLBExportImplementation().execute(context)
        if not exported.success:raise RuntimeError(exported.message)
        row['glb']={'path':str(target.relative_to(args.output)),'sha256':sha(target)}
        row['export_metrics']=exported.metrics;row['export_metadata']=exported.metadata
        for image in bpy.data.images:
            if image.has_data:
                try:image.pack()
                except RuntimeError:pass
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'source.blend'))
        row['source_projection_space']=dict(width=space.width,depth=space.depth,height=space.height,
            voxel_size=space.voxel_size,center_xy=space.center_xy)
        report['cases'].append(row);write(args.output/'report.json',report)
        print('DUMMY_QUALITY',name,'completed',flush=True)
    report['technical_status']='completed';write(args.output/'report.json',report)


if __name__=='__main__':main()
