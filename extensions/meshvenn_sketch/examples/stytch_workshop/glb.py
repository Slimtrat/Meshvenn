"""Inspect standard GLB and produce exact native-mount-local static attachments."""
import hashlib
import json
import struct
from mathutils import Matrix,Quaternion,Vector

FORMATS={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}
WIDTH={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}


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
    accessor=doc['accessors'][index];view=doc['bufferViews'][accessor['bufferView']]
    fmt='<'+FORMATS[accessor['componentType']]*WIDTH[accessor['type']]
    start=view.get('byteOffset',0)+accessor.get('byteOffset',0);stride=view.get('byteStride',struct.calcsize(fmt))
    return [struct.unpack_from(fmt,binary,start+i*stride) for i in range(accessor['count'])]


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
    mesh_index=next(i for i,n in enumerate(doc['nodes']) if 'mesh' in n)
    joint=next(i for i in doc['skins'][0]['joints'] if doc['nodes'][i]['name']==module['parent_joint'])
    mount=matrices[joint] @ (transform(socket) if socket else Matrix.Identity(4))
    # A skinned glTF node's transform is not a mesh-to-world transform. Skin
    # palettes own that mapping; Blender may already bake meters into positions.
    skin=doc['skins'][0];bind=values(doc,binary,skin['inverseBindMatrices'])[skin['joints'].index(joint)]
    inverse_bind=Matrix([bind[i:i+4] for i in range(0,16,4)]).transposed()
    change=mount.inverted() @ matrices[joint] @ inverse_bind
    normals=change.to_3x3().inverted().transposed()
    output={'asset':{'version':'2.0','generator':'Meshvenn Sketch workshop modules'},
            'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':module['id'],'mesh':0}],
            'meshes':[{'primitives':[]}],'materials':doc.get('materials',[]),'bufferViews':[],'accessors':[]}
    data=bytearray()
    def add(rows,kind,component=5126):
        data.extend(b'\0'*(-len(data)%4));start=len(data)
        fmt='<'+FORMATS[component]*WIDTH[kind]
        for row in rows:data.extend(struct.pack(fmt,*row))
        vi=len(output['bufferViews']);output['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start})
        ai=len(output['accessors']);accessor={'bufferView':vi,'componentType':component,'count':len(rows),'type':kind}
        if kind=='VEC3':accessor.update(min=[min(r[i] for r in rows) for i in range(3)],max=[max(r[i] for r in rows) for i in range(3)])
        output['accessors'].append(accessor);return ai
    for primitive in doc['meshes'][doc['nodes'][mesh_index]['mesh']]['primitives']:
        source=primitive['attributes']
        joints=values(doc,binary,source['JOINTS_0']);weights=values(doc,binary,source['WEIGHTS_0'])
        if any(sum(w>0 for w in row)!=1 or abs(sum(row)-1)>1e-6 or any(skin['joints'][i]!=joint for i,w in zip(indices,row) if w>0) for indices,row in zip(joints,weights)):
            raise ValueError('Only single-native-joint modules have static attachment variants')
        attributes={'POSITION':add([change @ Vector(p) for p in values(doc,binary,source['POSITION'])],'VEC3')}
        if 'NORMAL' in source:attributes['NORMAL']=add([(normals @ Vector(n)).normalized() for n in values(doc,binary,source['NORMAL'])],'VEC3')
        if 'TEXCOORD_0' in source:attributes['TEXCOORD_0']=add(values(doc,binary,source['TEXCOORD_0']),'VEC2')
        output['meshes'][0]['primitives'].append({'attributes':attributes,'indices':add(values(doc,binary,primitive['indices']),'SCALAR',5125),'material':primitive.get('material',0)})
    output['buffers']=[{'byteLength':len(data)}]
    write(destination,output,bytes(data))
    return {'kind':'native-socket-local' if socket else 'native-joint-local','parent_joint':module['parent_joint'],
            'socket_id':module['socket_id'],'local_transform':'identity','inherits_native_normalization':True,
            'rest_mount_world':[list(row) for row in mount]}
