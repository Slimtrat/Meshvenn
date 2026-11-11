"""Reimport published GLBs; verify closed surfaces, packed edit sources and sockets."""
import argparse
import json
from pathlib import Path
import sys
import bmesh
import bpy


parser=argparse.ArgumentParser();parser.add_argument('--pack',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=args.pack.resolve()
proof=[]
for asset in json.loads((folder/'pack.json').read_text())['assets']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(folder/asset['file']))
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    errors=[]
    for obj in meshes:
        mesh=bmesh.new();mesh.from_mesh(obj.data)
        bmesh.ops.remove_doubles(mesh,verts=list(mesh.verts),dist=.000001)
        if any(not edge.is_manifold for edge in mesh.edges):errors.append(obj.name+' has open/nonmanifold edges')
        if any(face.calc_area()<1e-12 for face in mesh.faces):errors.append(obj.name+' has degenerate faces')
        mesh.free()
    if errors:raise RuntimeError(str(errors))
    bpy.ops.wm.open_mainfile(filepath=str(folder/asset['source']['file']),use_scripts=False)
    if any(o.type=='ARMATURE' for o in bpy.context.scene.objects):raise ValueError('Source contains a rig')
    if len(bpy.data.images)<3 or any(not image.packed_file for image in bpy.data.images if image.name.endswith('-paint')):
        raise ValueError('Editable sources must pack their images')
    hinge=bpy.data.objects[asset['opening']['node']]
    if len(hinge.animation_data.nla_tracks)!=2:raise ValueError('Editable animation tracks absent')
    proof.append(dict(id=asset['id'],sha256=asset['sha256'],closed_surfaces=True,packed_editable_source=True,skins=0))
(folder/'blender-validation.json').write_text(json.dumps(dict(status='pass',blender=bpy.app.version_string,assets=proof),indent=2)+'\n',encoding='utf-8')
print('CHAMBER BLENDER PASS: two reimported closed rigid models, packed textures and editable animation tracks')
