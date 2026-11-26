"""Pose exact trial GLBs using fixed cameras and baseline joint neighborhoods."""
from contextlib import ExitStack
import argparse,hashlib,json,math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.glb_v2_pose_support import evaluated_positions,rotated_bone
from scripts.glb_v2_pose_metrics import joint_edge_summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trials',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    a.trials=a.trials.resolve();a.output=a.output.resolve()
    a.output.mkdir(parents=True,exist_ok=False)
    trials=json.loads((a.trials/'report.json').read_text());report=dict(schema_version=1,
        scope='Matched GLB poses and local edge distortion; not anatomy, volume or consumer acceptance',
        quality_certification='unknown',cases=[])
    if not trials['cases'] or trials['cases'][0]['id']!='baseline':
        raise ValueError('Require the pinned baseline before candidate poses')
    baseline=None;centers=None
    for case in trials['cases']:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        glb=a.trials/case['glb']['path']
        assert hashlib.sha256(glb.read_bytes()).hexdigest()==case['glb']['sha256']
        bpy.ops.import_scene.gltf(filepath=str(glb.resolve()),disable_bone_shape=True)
        mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH')
        rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        rest=evaluated_positions(mesh);mesh.data.calc_loop_triangles()
        triangles=tuple(tuple(t.vertices) for t in mesh.data.loop_triangles)
        if baseline is None:
            baseline=rest
            centers={b.name:tuple(rig.matrix_world@b.head) for b in rig.pose.bones}
        assert len(baseline)==len(rest)
        error=max(math.dist(x,y) for x,y in zip(baseline,rest))
        assert error<2e-5
        height=max(v[2] for v in baseline)-min(v[2] for v in baseline)
        row=dict(id=case['id'],glb_sha256=case['glb']['sha256'],rest_error_vs_baseline=error,
                 common_joint_centers=centers,probes=[],frames=[])
        for family,axes in (('forearm',(('Y',(0,1,0)),('Z',(0,0,1)))),('shin',(('X',(1,0,0)),))):
            for side in ('L','R'):
                name=family+'.'+side
                for label,axis in axes:
                    for degrees in (-90,-45,45,90):
                        with rotated_bone(rig,name,degrees,axis,world_space=True):
                            posed=evaluated_positions(mesh)
                        row['probes'].append(dict(id=f'{name}/{label}/{degrees:+d}',
                            edges=joint_edge_summary(rest,posed,triangles,centers[name],height,touching=True)))
        restore_error=max(math.dist(x,y) for x,y in zip(rest,evaluated_positions(mesh)))
        assert restore_error<1e-6
        row['rest_restore_max_error']=restore_error
        row['frames']=render(mesh,rig,a.output/case['id'])
        report['cases'].append(row)
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    report['technical_status']='completed';(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')


def render(mesh,rig,out):
    out.mkdir()
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32;scene.cycles.use_denoising=False
    scene.render.resolution_x=scene.render.resolution_y=512;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.world=bpy.data.worlds.new('ReviewWorld');scene.world.color=(.09,.10,.13)
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
    camera_data=bpy.data.cameras.new('ReviewCamera');camera=bpy.data.objects.new('ReviewCamera',camera_data)
    scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO';camera_data.ortho_scale=2.4
    center=Vector((0,0,1))
    for name,position,energy in (('key',(3,-4,5),500),('fill',(-4,-2,2),250),('rim',(1,4,4),350)):
        light=bpy.data.lights.new(name,'AREA');light.energy=energy;light.shape='DISK';light.size=4
        obj=bpy.data.objects.new(name,light);scene.collection.objects.link(obj);obj.location=center+Vector(position)
        obj.rotation_euler=(center-obj.location).to_track_quat('-Z','Y').to_euler()
    clay=bpy.data.materials.new('GeometryClay');clay.use_nodes=True
    shader=clay.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(.56,.62,.7,1);shader.inputs['Roughness'].default_value=1
    frames=[]
    for name,rotations,angle in (
        ('arms-down',(('upper_arm.L',70,(0,1,0)),('upper_arm.R',-70,(0,1,0))),45),
        ('elbows90',(('forearm.L',90,(0,1,0)),('forearm.R',-90,(0,1,0))),45),
        ('knee90',(('shin.L',90,(1,0,0)),),90)):
        with ExitStack() as stack:
            for bone,degrees,axis in rotations:stack.enter_context(rotated_bone(rig,bone,degrees,axis,world_space=True))
            theta=math.radians(angle);camera.location=center+Vector((math.sin(theta)*5,-math.cos(theta)*5,.1))
            camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
            for mode in ('material','clay'):
                scene.view_layers[0].material_override=clay if mode=='clay' else None
                target=out/f'{name}-{mode}.png';scene.render.filepath=str(target);bpy.ops.render.render(write_still=True)
                frames.append(dict(pose=name,mode=mode,path=out.name+'/'+target.name,
                    sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    camera=dict(location=list(camera.location),ortho_scale=camera_data.ortho_scale)))
    return frames


if __name__=='__main__':main()
