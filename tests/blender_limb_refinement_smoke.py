"""Actual static source: staged distal edit, exact rollback and protected authority."""
import argparse
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root',type=Path,default=repository)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--variant',type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    root=args.package_root.resolve()
    output=args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Choose an empty verification output directory.')
    sys.path.insert(0,str(root.parent)); sys.path.insert(0,str(repository))
    package=importlib.import_module(root.name)
    package.register()
    try:
        module=lambda name: importlib.import_module(root.name+'.'+name)
        fixture=repository/'example/v2/modular/StytchDollShoulderAligned'
        bpy.ops.wm.open_mainfile(filepath=str(fixture/'source.blend'),use_scripts=False)
        mesh,rig=bpy.data.objects['MeshvennScan'],bpy.data.objects['MeshvennCanonicalRig']
        spec=module('implementations.glb_export.face_authoring')._read(fixture/'authoring.json')
        api=module('implementations.canonical_rig_v2.limb_refinement')
        from scripts.author_stytch_doll import source_snapshot
        before=source_snapshot(mesh,rig); original=mesh.data; properties=dict(mesh.items())
        objects,meshes=set(bpy.data.objects),set(bpy.data.meshes)
        def unchanged():
            assert mesh.data is original
            assert source_snapshot(mesh,rig)==before
            assert dict(mesh.items())==properties
            assert set(bpy.data.objects)==objects and set(bpy.data.meshes)==meshes
        def perform():
            with api.refine_authored_distal_limbs(mesh,spec): pass
        def rejected(call):
            try: call()
            except (TypeError,ValueError): return
            raise AssertionError('Unsafe distal skin edit accepted')
        other=bpy.data.objects.new('SharedLimbSourceTest',mesh.data)
        try: rejected(perform)
        finally: bpy.data.objects.remove(other)
        unchanged()
        shared=bpy.data.objects.new('SharedLimbRigTest',rig.data)
        try: rejected(perform)
        finally: bpy.data.objects.remove(shared)
        unchanged()
        action=bpy.data.actions.new('NoDistalAnimationMigration')
        rig.animation_data_create().action=action
        try: rejected(perform)
        finally:
            rig.animation_data_clear()
            bpy.data.actions.remove(action)
        unchanged()
        rig.pose.bones['thigh.L'].rotation_mode='XYZ'
        rig.pose.bones['thigh.L'].rotation_euler.x=.1
        bpy.context.view_layer.update()
        rejected(perform)
        rig.pose.bones['thigh.L'].matrix_basis.identity()
        bpy.context.view_layer.update()
        unchanged()
        with patch.object(api.json,'dumps',side_effect=RuntimeError('Injected post-assignment failure')):
            try: perform()
            except RuntimeError: pass
            else: raise AssertionError('Failure injection missed')
        unchanged()
        try:
            with api.refine_authored_distal_limbs(mesh,spec):
                raise RuntimeError('Injected caller failure')
        except RuntimeError: pass
        unchanged()
        mesh.hide_set(False)
        bpy.ops.object.select_all(action='DESELECT'); mesh.select_set(True)
        bpy.context.view_layer.objects.active=mesh
        assert bpy.ops.bpt.refine_distal_limb_skin()=={'FINISHED'}
        after=source_snapshot(mesh,rig)
        assert {k:v for k,v in before.items() if k!='weights'}=={k:v for k,v in after.items() if k!='weights'}
        assert rig.data is not None and mesh.data is not original
        assert set(bpy.data.objects)==objects
        report=json.loads(mesh['meshvenn_distal_limb_refinement'])
        assert report['changed_vertex_count']>0
        assert before['weights']!=after['weights']
        from core.rig_owned_skin import _surface_distances
        points=[tuple(v.co) for v in mesh.data.vertices]
        height=max(p[2] for p in points)-min(p[2] for p in points)
        keys,members,_,_=_surface_distances(points,[tuple(f.vertices) for f in mesh.data.polygons],spec.ownership[mesh.name],height)
        for key,old,new in zip(keys,before['weights'],after['weights']):
            if 'body-core' in members[key]: assert old==new
        rejected(perform)
        assert source_snapshot(mesh,rig)==after
        output.mkdir(parents=True,exist_ok=True)
        relocated_proof=None
        if args.variant:
            variant=args.variant.resolve(strict=True)
            relocated=output/'relocated'
            relocated.mkdir()
            for name in ('source.blend','authoring.json'):
                shutil.copy2(variant/name,relocated/name)
            bpy.ops.wm.open_mainfile(filepath=str(relocated/'source.blend'),use_scripts=False)
            mesh,rig=bpy.data.objects['MeshvennScan'],bpy.data.objects['MeshvennCanonicalRig']
            selected=source_snapshot(mesh,rig)
            bpy.context.scene.bpt_settings.export_output_path='//reexport.glb'
            assert bpy.ops.bpt.export_existing_modular_source()=={'FINISHED'}
            assert source_snapshot(mesh,rig)==selected
            pipeline=module('operators.runtime').get_last_pipeline_context(bpy.context.scene)
            result=pipeline.require_output(module('core.pipeline_contracts').PipelineStage.EXPORT)
            reader=module('implementations.glb_export.modular_gltf')
            from scripts.workshop_doll_evidence import compare_reference
            old,old_binary=reader.read_glb(variant/'character.glb')
            new,new_binary=reader.read_glb(result.path)
            relocated_proof=compare_reference(old,old_binary,new,new_binary,reader.read_accessor)
            assert relocated_proof['max_weight_error']==relocated_proof['max_inverse_bind_error']==0
        (output/'report.json').write_text(json.dumps({'passed':True,'exact_rollback':True,
            'body_rig_surface_atlas_preserved':True,'edit':report,
            'relocated_proof':relocated_proof},indent=2)+'\n','utf-8')
        print('Distal limb skin PASS: exact rollback, distal native chains only, unchanged body/rig/surface/atlas.')
    finally: package.unregister()


if __name__=='__main__': main()
