"""Render the actual delivered GLBs in their closed and open states."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pack',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=args.pack.resolve()
    output=folder/'previews';output.mkdir(exist_ok=True)
    for asset in json.loads((folder/'pack.json').read_text())['assets']:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(folder/asset['file']))
        scene=bpy.context.scene
        # Import animation exists, but render poses are deliberately explicit for comparable views.
        hinge=bpy.data.objects[asset['opening']['node']]
        for obj in list(scene.objects):
            if obj.animation_data:obj.animation_data_clear()
        world=bpy.data.worlds.new('Chamber studio');world.use_nodes=True;scene.world=world
        world.node_tree.nodes['Background'].inputs['Color'].default_value=(.085,.12,.14,1)
        world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
        data=bpy.data.cameras.new('Evidence');camera=bpy.data.objects.new('Evidence',data);scene.collection.objects.link(camera);scene.camera=camera
        data.type='ORTHO'
        is_door=asset['id']=='chamber-door-v1'
        target=Vector((0,0,.88 if is_door else .37));camera.location=(2.0,-5,2.4 if is_door else 2.1)
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();data.ortho_scale=2.35 if is_door else 1.4
        for name,location,power,color,size in (
            ('Warm key',(-3,-4,4),430,(1,.84,.61),3),
            ('Cool fill',(3,-2,3),220,(.51,.78,1),3),
            ('Rim',(0,3,3),320,(.64,.85,1),2)):
            light=bpy.data.lights.new(name,'AREA');light.energy=power;light.color=color;light.shape='DISK';light.size=size
            obj=bpy.data.objects.new(name,light);scene.collection.objects.link(obj);obj.location=location
            obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
        bpy.ops.mesh.primitive_plane_add(size=200)
        floor=bpy.context.object;mat=bpy.data.materials.new('Preview ground');mat.diffuse_color=(.042,.06,.065,1);floor.data.materials.append(mat)
        scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
        scene.render.resolution_x=800;scene.render.resolution_y=900 if is_door else 650;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
        for state in ('closed','open'):
            hinge.rotation_mode='XYZ';hinge.rotation_euler=(0,0,0)
            hinge.rotation_euler[2 if is_door else 0]=math.radians(asset['opening']['angle_degrees']) if state=='open' else 0
            scene.render.filepath=str(output/(asset['id']+'-'+state+'.png'))
            bpy.ops.render.render(write_still=True)
    print('CHAMBER RENDER PASS: four exported-GLB views.')


if __name__=='__main__':main()
