"""Inspect standard GLB and produce exact native-mount-local static attachments."""
import hashlib
import base64
from copy import deepcopy
import json
import math
import struct
from mathutils import Matrix,Quaternion,Vector

FORMATS={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}
WIDTH={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
# These extensions retain material/texture references only. Geometry codecs,
# animation pointers and world-distance volume parameters need another bake.
STATIC_EXTENSIONS={'KHR_texture_transform','KHR_texture_basisu','EXT_texture_webp','EXT_texture_avif',
    'KHR_materials_unlit','KHR_materials_clearcoat','KHR_materials_sheen','KHR_materials_specular',
    'KHR_materials_ior','KHR_materials_transmission','KHR_materials_emissive_strength',
    'KHR_materials_iridescence','KHR_materials_anisotropy','KHR_materials_pbrSpecularGlossiness',
    'KHR_materials_variants'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    raw=path.read_bytes()
    if struct.unpack_from('<4sII',raw)!=(b'glTF',2,len(raw)):raise ValueError('Invalid GLB')
    size,kind=struct.unpack_from('<II',raw,12)
    if kind!=0x4E4F534A:raise ValueError('Missing JSON')
    doc=json.loads(raw[20:20+size]);offset=20+size
    length,kind=struct.unpack_from('<II',raw,offset)
    if kind!=0x004E4942:raise ValueError('Missing binary')
    return doc,raw[offset+8:offset+8+length]


def write(path,doc,binary):
    data=json.dumps(doc,separators=(',',':'),allow_nan=False).encode();data+=b' '*(-len(data)%4)
    binary+=b'\0'*(-len(binary)%4)
    body=struct.pack('<II',len(data),0x4E4F534A)+data+struct.pack('<II',len(binary),0x004E4942)+binary
    path.write_bytes(struct.pack('<4sII',b'glTF',2,len(body)+12)+body)


def values(doc,binary,index):
    accessor=doc['accessors'][index]
    if 'sparse' in accessor or 'bufferView' not in accessor:raise ValueError('Sparse/accessor-only data must be baked before static export')
    view=doc['bufferViews'][accessor['bufferView']]
    if view.get('buffer',0)!=0:raise ValueError('Static export requires a single embedded GLB buffer')
    fmt='<'+FORMATS[accessor['componentType']]*WIDTH[accessor['type']]
    start=view.get('byteOffset',0)+accessor.get('byteOffset',0);stride=view.get('byteStride',struct.calcsize(fmt))
    count=accessor['count'];end=start+(count-1)*stride+struct.calcsize(fmt)
    if count<=0 or start<view.get('byteOffset',0) or start<0 or stride<struct.calcsize(fmt) or end>view.get('byteOffset',0)+view['byteLength'] or end>len(binary):
        raise ValueError('Accessor lies outside its embedded buffer view')
    result=[struct.unpack_from(fmt,binary,start+i*stride) for i in range(count)]
    if accessor.get('normalized',False):
        divisor={5120:127.,5121:255.,5122:32767.,5123:65535.}.get(accessor['componentType'])
        if divisor is None:raise ValueError('Only 8/16-bit integer accessors can be normalized')
        result=[tuple(max(-1.,v/divisor) for v in row) for row in result]
    return result


def _static_extensions(doc):
    declared=set(doc.get('extensionsUsed',()))|set(doc.get('extensionsRequired',()))
    def visit(value):
        if isinstance(value,dict):
            declared.update(value.get('extensions',{}))
            for key,item in value.items():
                if key!='extras':visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    visit(doc)
    unsupported=declared-STATIC_EXTENSIONS
    if unsupported:raise ValueError('Static export cannot preserve these extensions: '+', '.join(sorted(unsupported)))


def _image_payload(doc,binary,image):
    if 'uri' in image:
        uri=image['uri']
        if not uri.startswith('data:') or ';base64,' not in uri:
            raise ValueError('Pack external images into the GLB before static export')
        header,payload=uri.split(',',1)
        return base64.b64decode(payload,validate=True),header[5:].split(';',1)[0]
    if 'bufferView' not in image:raise ValueError('Embedded image has no payload')
    view=doc['bufferViews'][image['bufferView']]
    start=view.get('byteOffset',0);length=view['byteLength']
    if view.get('buffer',0)!=0 or start<0 or length<=0 or start+length>len(binary):
        raise ValueError('Image lies outside the embedded GLB buffer')
    if not image.get('mimeType'):raise ValueError('Embedded image needs an explicit MIME type')
    return binary[start:start+length],image['mimeType']


def transform(node):
    if 'matrix' in node:return Matrix([node['matrix'][i:i+4] for i in range(0,16,4)]).transposed()
    x,y,z,w=node.get('rotation',(0,0,0,1))
    return Matrix.LocRotScale(Vector(node.get('translation',(0,0,0))),Quaternion((w,x,y,z)),Vector(node.get('scale',(1,1,1))))


def worlds(doc):
    parents={child:i for i,n in enumerate(doc['nodes']) for child in n.get('children',[])};cache={}
    def world(i):
        if i not in cache:cache[i]=(world(parents[i]) if i in parents else Matrix.Identity(4)) @ transform(doc['nodes'][i])
        return cache[i]
    return [world(i) for i in range(len(doc['nodes']))]


def joint_profile(doc,binary):
    skin=doc['skins'][0];matrices=worlds(doc);inverse=values(doc,binary,skin['inverseBindMatrices'])
    return {doc['nodes'][node]['name']:{'world':[list(row) for row in matrices[node]],'inverse_bind':list(bind)}
            for node,bind in zip(skin['joints'],inverse)}


def check_rig(doc,binary,reference):
    actual=joint_profile(doc,binary)
    if set(actual)!=set(reference):raise ValueError('Native joint names changed')
    for name,expected in reference.items():
        for key in ('world','inverse_bind'):
            a=actual[name][key];b=expected[key]
            flat=lambda xs:[n for row in xs for n in row] if isinstance(xs[0],list) else xs
            if max(abs(x-y) for x,y in zip(flat(a),flat(b)))>2e-5:raise ValueError(f'Native {key} changed: {name}')


def module_metadata(path,metadata):
    doc,binary=read(path)
    doc['asset'].setdefault('extras',{})['meshvenn_module_asset']=metadata
    write(path,doc,binary)


def attachment(skinned_path,destination,module,socket):
    doc,binary=read(skinned_path);matrices=worlds(doc)
    _static_extensions(doc)
    meshes=[i for i,n in enumerate(doc['nodes']) if 'mesh' in n]
    if len(meshes)!=1 or len(doc.get('skins',[]))!=1 or doc.get('animations'):
        raise ValueError('Static attachments require one skinned module and no animation')
    mesh_index=meshes[0];source_mesh=doc['meshes'][doc['nodes'][mesh_index]['mesh']]
    if source_mesh.get('weights') or doc['nodes'][mesh_index].get('weights') or any(p.get('targets') for p in source_mesh['primitives']):
        raise ValueError('Bake shape keys before static attachment export')
    joint=next(i for i in doc['skins'][0]['joints'] if doc['nodes'][i]['name']==module['parent_joint'])
    mount=matrices[joint] @ (transform(socket) if socket else Matrix.Identity(4))
    # A skinned glTF node's transform is not a mesh-to-world transform. Skin
    # palettes own that mapping; Blender may already bake meters into positions.
    skin=doc['skins'][0];bind=values(doc,binary,skin['inverseBindMatrices'])[skin['joints'].index(joint)]
    inverse_bind=Matrix([bind[i:i+4] for i in range(0,16,4)]).transposed()
    change=mount.inverted() @ matrices[joint] @ inverse_bind
    if not math.isfinite(change.determinant()) or change.determinant()<=1e-12:
        raise ValueError('Static export requires a positive nonsingular mount/skin transform')
    normals=change.to_3x3().inverted().transposed()
    output={'asset':{'version':'2.0','generator':'Meshvenn Sketch workshop modules'},
            'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':module['id'],'mesh':0}],
            'meshes':[{'primitives':[]}],'materials':deepcopy(doc.get('materials',[])),'bufferViews':[],'accessors':[]}
    for key in ('extensionsUsed','extensionsRequired','extensions','samplers','textures'):
        if key in doc:output[key]=deepcopy(doc[key])
    data=bytearray()
    def add(rows,kind,component=5126):
        data.extend(b'\0'*(-len(data)%4));start=len(data)
        fmt='<'+FORMATS[component]*WIDTH[kind]
        for row in rows:data.extend(struct.pack(fmt,*row))
        vi=len(output['bufferViews']);output['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start})
        ai=len(output['accessors']);accessor={'bufferView':vi,'componentType':component,'count':len(rows),'type':kind}
        if kind=='VEC3':accessor.update(min=[min(r[i] for r in rows) for i in range(3)],max=[max(r[i] for r in rows) for i in range(3)])
        output['accessors'].append(accessor);return ai
    for primitive in source_mesh['primitives']:
        source=primitive['attributes']
        if 'indices' not in primitive:raise ValueError('Index primitives before static attachment export')
        for name in source:
            if name in {'POSITION','NORMAL','TANGENT','JOINTS_0','WEIGHTS_0'}:continue
            if any(name.startswith(prefix) and name[len(prefix):].isdigit() for prefix in ('TEXCOORD_','COLOR_')):continue
            raise ValueError('Static export cannot preserve vertex attribute '+name)
        joints=values(doc,binary,source['JOINTS_0']);weights=values(doc,binary,source['WEIGHTS_0'])
        if any(sum(w>0 for w in row)!=1 or abs(sum(row)-1)>1e-6 or any(skin['joints'][i]!=joint for i,w in zip(indices,row) if w>0) for indices,row in zip(joints,weights)):
            raise ValueError('Only single-native-joint modules have static attachment variants')
        attributes={'POSITION':add([change @ Vector(p) for p in values(doc,binary,source['POSITION'])],'VEC3')}
        if 'NORMAL' in source:attributes['NORMAL']=add([(normals @ Vector(n)).normalized() for n in values(doc,binary,source['NORMAL'])],'VEC3')
        if 'TANGENT' in source:
            attributes['TANGENT']=add([tuple((change.to_3x3() @ Vector(t[:3])).normalized())+(t[3],) for t in values(doc,binary,source['TANGENT'])],'VEC4')
        for name,index in source.items():
            if name.startswith(('TEXCOORD_','COLOR_')):attributes[name]=add(values(doc,binary,index),doc['accessors'][index]['type'])
        exported={'attributes':attributes,'indices':add(values(doc,binary,primitive['indices']),'SCALAR',5125)}
        for key in ('material','mode','extensions','extras'):
            if key in primitive:exported[key]=deepcopy(primitive[key])
        output['meshes'][0]['primitives'].append(exported)
    if doc.get('images'):
        output['images']=[]
        for image in doc['images']:
            payload,mime=_image_payload(doc,binary,image)
            data.extend(b'\0'*(-len(data)%4));start=len(data);data.extend(payload)
            view=len(output['bufferViews'])
            output['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(payload)})
            copied=deepcopy(image);copied.pop('uri',None);copied.update(bufferView=view,mimeType=mime)
            output['images'].append(copied)
    output['buffers']=[{'byteLength':len(data)}]
    write(destination,output,bytes(data))
    return {'kind':'native-socket-local' if socket else 'native-joint-local','parent_joint':module['parent_joint'],
            'socket_id':module['socket_id'],'local_transform':'identity','inherits_native_normalization':True,
            'rest_mount_world':[list(row) for row in mount]}
