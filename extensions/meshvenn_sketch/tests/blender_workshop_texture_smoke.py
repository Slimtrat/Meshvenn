"""Embedded textures, material semantics and normalized vertex data survive attachment export."""
import argparse
import base64
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
import sys
import zlib

import bpy
from mathutils import Euler,Matrix,Vector

HERE=Path(__file__).resolve().parents[1]/'examples/stytch_workshop'
sys.path.insert(0,str(HERE))
import glb

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=args.output.resolve()
folder.mkdir(parents=True,exist_ok=False)


def png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    pixels=bytes((255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(b'\0'+pixels[:8]+b'\0'+pixels[8:]))+chunk(b'IEND',b''))


def flatten(matrix):return [v for col in matrix.transposed() for v in col]


def fixture():
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
         'bufferViews':[],'accessors':[],'meshes':[{'primitives':[]}],
         'samplers':[{'magFilter':9728,'minFilter':9728,'wrapS':33071,'wrapT':33648},
                     {'magFilter':9729,'minFilter':9987,'wrapS':10497,'wrapT':10497}],
         'textures':[{'source':0,'sampler':0},{'source':0,'sampler':1}],
         'materials':[{'name':'Fixture canvas','doubleSided':True,
                       'pbrMetallicRoughness':{'baseColorTexture':{'index':0,'texCoord':1,
                           'extensions':{'KHR_texture_transform':{'offset':[.125,.25],'rotation':.3,'scale':[.7,.8],'texCoord':1}}}},
                       'extensions':{'KHR_materials_unlit':{}}},
                      {'name':'Fixture coated','pbrMetallicRoughness':{'baseColorTexture':{'index':1}},
                       'extensions':{'KHR_materials_clearcoat':{'clearcoatFactor':.4,'clearcoatRoughnessFactor':.2,
                           'clearcoatTexture':{'index':1,'texCoord':1}}}}],
         'extensionsUsed':['KHR_texture_transform','KHR_materials_unlit','KHR_materials_clearcoat','KHR_materials_variants'],
         'extensionsRequired':['KHR_texture_transform'],
         'extensions':{'KHR_materials_variants':{'variants':[{'name':'Alternate canvas'}]}}}
    binary=bytearray()
    def add(rows,kind,component=5126,normalized=False):
        binary.extend(b'\0'*(-len(binary)%4));start=len(binary)
        fmt='<'+glb.FORMATS[component]*glb.WIDTH[kind]
        for row in rows:binary.extend(struct.pack(fmt,*row))
        view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(binary)-start})
        index=len(doc['accessors']);accessor={'bufferView':view,'componentType':component,'count':len(rows),'type':kind}
        if normalized:accessor['normalized']=True
        if kind=='VEC3':accessor.update(min=[min(r[i] for r in rows) for i in range(3)],max=[max(r[i] for r in rows) for i in range(3)])
        doc['accessors'].append(accessor);return index
    positions=((0,0,0),(1,0,0),(1,1,0),(0,1,0))
    attributes={'POSITION':add(positions,'VEC3'),'NORMAL':add([(0,0,1)]*4,'VEC3'),
                'TANGENT':add([(1,0,0,1)]*4,'VEC4'),
                'TEXCOORD_0':add(((0,0),(1,0),(1,1),(0,1)),'VEC2'),
                'TEXCOORD_1':add(((6553,13107),(52428,13107),(52428,58981),(6553,58981)),'VEC2',5123,True),
                'COLOR_0':add(((255,128,64,255),(64,255,128,255),(128,64,255,255),(255,255,255,255)),'VEC4',5121,True),
                'JOINTS_0':add([(0,0,0,0)]*4,'VEC4',5121),
                'WEIGHTS_0':add([(65535,0,0,0)]*4,'VEC4',5123,True)}
    for i,triangle in enumerate(((0,1,2),(0,2,3))):
        primitive={'attributes':attributes.copy(),'indices':add([(v,) for v in triangle],'SCALAR',5123),'material':i,'mode':4}
        if i==0:primitive['extensions']={'KHR_materials_variants':{'mappings':[{'material':1,'variants':[0]}]}}
        doc['meshes'][0]['primitives'].append(primitive)
    root=Matrix.LocRotScale(Vector((.25,.5,-.1)),Euler((.1,.2,.3)).to_quaternion(),Vector((.4,.4,.4)))
    bone=Matrix.LocRotScale(Vector((.3,.2,.1)),Euler((.2,-.1,.15)).to_quaternion(),Vector((1,1,1)))
    bind_world=Matrix.LocRotScale(Vector((.3,.8,-.4)),Euler((-.1,.3,.2)).to_quaternion(),Vector((1,1,1)))
    inverse=(root @ bone).inverted() @ bind_world
    ibm=add([flatten(inverse)],'MAT4')
    doc['nodes']=[{'name':'Fixture normalization','matrix':flatten(root),'children':[1,2]},
                  {'name':'fixture.head','matrix':flatten(bone)},
                  {'name':'Textured module','mesh':0,'skin':0}]
    doc['skins']=[{'joints':[1],'skeleton':1,'inverseBindMatrices':ibm}]
    binary.extend(b'\0'*(-len(binary)%4));start=len(binary);binary.extend(png())
    image_view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(png())})
    doc['images']=[{'name':'Fixture checker','mimeType':'image/png','bufferView':image_view}]
    doc['buffers']=[{'byteLength':len(binary)}]
    return doc,bytes(binary),positions,bind_world


def imported(path):
    before=set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path),disable_bone_shape=True)
    meshes=[o for o in set(bpy.context.scene.objects)-before if o.type=='MESH']
    assert len(meshes)==1
    return meshes[0]


def corners(mesh):
    assert len(mesh.data.uv_layers)==2 and len(mesh.data.color_attributes)==1
    color=mesh.data.color_attributes[0]
    result=[]
    for polygon in mesh.data.polygons:
        for loop in polygon.loop_indices:
            index=loop if color.domain=='CORNER' else mesh.data.loops[loop].vertex_index
            uv=[float(v) for layer in mesh.data.uv_layers for v in layer.data[loop].uv]
            result.append((mesh.data.materials[polygon.material_index].name.split('.')[0],
                           tuple(round(v,5) for v in uv+list(color.data[index].color))))
    return sorted(result)


def image_samples(mesh):
    samples=[];uv1=False
    for material in mesh.data.materials:
        for node in material.node_tree.nodes:
            if node.type=='TEX_IMAGE':
                assert tuple(node.image.size)==(2,2) and node.image.has_data
                samples.append(tuple(round(v,5) for v in node.image.pixels))
            if node.type=='UVMAP' and node.uv_map==mesh.data.uv_layers[1].name:uv1=True
    assert samples and uv1
    return samples


doc,binary,positions,bind_world=fixture()
source=folder/'textured-skinned.glb';output=folder/'textured-static.glb'
glb.write(source,doc,binary)
module={'id':'fixture-textured','parent_joint':'fixture.head','socket_id':'fixture.socket'}
rotation=Euler((.08,.15,-.1)).to_quaternion()
socket={'translation':[.2,-.15,.1],'rotation':[rotation.x,rotation.y,rotation.z,rotation.w],'scale':[1.1,.9,1.25]}
binding=glb.attachment(source,output,module,socket)
assert binding['kind']=='native-socket-local' and binding['socket_id']=='fixture.socket'
assert binding['parent_joint']=='fixture.head' and binding['local_transform']=='identity' and binding['inherits_native_normalization']
result,data=glb.read(output)
assert not result.get('skins') and len(result['nodes'])==len(result['meshes'])==1
assert result['materials']==doc['materials'] and result['textures']==doc['textures'] and result['samplers']==doc['samplers']
for key in ('extensionsUsed','extensionsRequired','extensions'):assert result[key]==doc[key]
assert glb._image_payload(result,data,result['images'][0])==(png(),'image/png')
mount=Matrix(binding['rest_mount_world']);expected_change=mount.inverted() @ bind_world
normals=expected_change.to_3x3().inverted().transposed()
for original,primitive in zip(doc['meshes'][0]['primitives'],result['meshes'][0]['primitives']):
    assert primitive.get('extensions')==original.get('extensions')
    assert primitive['mode']==original['mode'] and primitive['material']==original['material']
    attrs=primitive['attributes'];assert set(attrs)=={'POSITION','NORMAL','TANGENT','TEXCOORD_0','TEXCOORD_1','COLOR_0'}
    for name in ('TEXCOORD_0','TEXCOORD_1','COLOR_0'):
        actual=glb.values(result,data,attrs[name]);expected=glb.values(doc,binary,original['attributes'][name])
        assert max(abs(a-b) for row,want in zip(actual,expected) for a,b in zip(row,want))<1e-6
        assert result['accessors'][attrs[name]]['componentType']==5126
    for raw,actual in zip(positions,glb.values(result,data,attrs['POSITION'])):
        assert ((mount @ Vector(actual))-(bind_world @ Vector(raw))).length<2e-6
    for actual in glb.values(result,data,attrs['NORMAL']):assert (Vector(actual)-(normals @ Vector((0,0,1))).normalized()).length<1e-6
    for actual in glb.values(result,data,attrs['TANGENT']):assert (Vector(actual[:3])-(expected_change.to_3x3() @ Vector((1,0,0))).normalized()).length<1e-6 and actual[3]==1

original_mesh=imported(source);original_corners=corners(original_mesh);original_images=image_samples(original_mesh)
static_mesh=imported(output)
assert static_mesh.find_armature() is None and corners(static_mesh)==original_corners
assert image_samples(static_mesh)==original_images
convert=Matrix.Rotation(-math.pi/2,4,'X')
raw_static=[expected_change @ Vector(p) for p in positions]
for vertex in static_mesh.data.vertices:
    actual=convert @ static_mesh.matrix_world @ vertex.co
    assert min((actual-p).length for p in raw_static)<2e-6

# Unsupported data must leave an existing destination intact, not publish a loss.
bad=folder/'unsupported.glb';protected=folder/'protected.glb';protected.write_bytes(b'preserved-existing-file')
def refused(changed):
    glb.write(bad,changed,binary)
    try:glb.attachment(bad,protected,module,socket)
    except ValueError:pass
    else:raise AssertionError('Lossy input was accepted')
    assert protected.read_bytes()==b'preserved-existing-file'
changed=deepcopy(doc);changed['images'][0]={'uri':'external.png'};refused(changed)
changed=deepcopy(doc);changed['meshes'][0]['primitives'][0]['targets']=[{'POSITION':0}];refused(changed)
changed=deepcopy(doc);changed['extensionsUsed'].append('KHR_draco_mesh_compression');refused(changed)
changed=deepcopy(doc);changed['extensionsUsed'].append('KHR_materials_volume');refused(changed)
changed=deepcopy(doc);changed['meshes'][0]['primitives'][0]['attributes']['_CUSTOM']=0;refused(changed)
changed=deepcopy(doc);changed['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0']]['normalized']=True;refused(changed)

# Portable data-URI images are embedded again, rather than made external.
embedded=deepcopy(doc);embedded['images'][0]={'uri':'data:image/png;base64,'+base64.b64encode(png()).decode(),'name':'Data URI checker'}
uri_source=folder/'data-uri.glb';uri_static=folder/'data-uri-static.glb'
glb.write(uri_source,embedded,binary);glb.attachment(uri_source,uri_static,module,socket)
uri_doc,uri_binary=glb.read(uri_static)
assert glb._image_payload(uri_doc,uri_binary,uri_doc['images'][0])==(png(),'image/png') and 'uri' not in uri_doc['images'][0]

# The six previously delivered, untextured attachments stay byte-identical.
pack_folder=HERE.parents[3]/'example/v2/modules/StytchWorkshopV1'
pack=json.loads((pack_folder/'pack.json').read_text());sockets={s['id']:s for s in pack['target']['sockets']}
for definition in pack['modules']:
    if 'attachment' not in definition:continue
    source_path=pack_folder/definition['skinned']['file'];destination=folder/(definition['id']+'.glb')
    source_doc,_=glb.read(source_path);metadata=source_doc['asset']['extras']['meshvenn_module_asset']
    mount=glb.attachment(source_path,destination,definition,sockets.get(definition['socket_id']))
    glb.module_metadata(destination,{**metadata,'binding':mount})
    assert glb.digest(destination)==definition['attachment']['sha256'],definition['id']+' changed unexpectedly'

(folder/'texture-validation.json').write_text(json.dumps({'schema_version':1,'embedded_image_exact':True,
    'uv_sets':2,'normalized_colors_preserved':True,'material_extensions_preserved':True,
    'source_static_import_match':True,'native_frame_error_m_limit':2e-6,'unsupported_cases_rejected':6,
    'unchanged_existing_attachments':6,'data_uri_embedded':True},indent=2)+'\n')
print('WORKSHOP TEXTURE PASS: exact embedded PNG, textures/samplers/material extensions, two UV sets, normalized colors/weights, tangents, source/static Blender imports and native socket placement; six lossy inputs refused without overwriting.')
