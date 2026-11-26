"""Standard-library GLB delivery checks, also used to assemble a verified ZIP."""
import hashlib
import json
from pathlib import Path
import struct


def require(condition, message):
    if not condition:raise ValueError(message)


def glb(path):
    data=path.read_bytes()
    magic,version,length=struct.unpack_from('<4sII',data)
    if (magic,version,length)!=(b'glTF',2,len(data)):raise ValueError('Invalid GLB header')
    count,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4e4f534a:raise ValueError('Missing JSON chunk')
    return json.loads(data[20:20+count])


def verify(folder):
    folder=Path(folder).resolve()
    document=json.loads((folder/'pack.json').read_text(encoding='utf-8'))
    require(document['pack_id']=='stytch-chamber-v1','Unexpected pack identity')
    require(len(document['assets'])==2,'Both props are required')
    for asset in document['assets']:
        for record in (asset,asset['source']):
            path=(folder/record['file']).resolve()
            require(path.is_relative_to(folder),'Asset path escapes pack')
            require(hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'],'Fingerprint mismatch: '+str(path))
        doc=glb(folder/asset['file'])
        require(not doc.get('skins') and not any('skin' in n for n in doc['nodes']),'Rigid prop contains a skin')
        require(set(asset['requiredNodes']).issubset(n.get('name') for n in doc['nodes']),'Missing contract nodes')
        names={n.get('name'):i for i,n in enumerate(doc['nodes'])}
        moving='DoorLeaf' if 'DoorLeaf' in names else 'ChestLid'
        require(names[moving] in doc['nodes'][names[asset['opening']['node']]]['children'],'Moving part lost its hinge parent')
        clips={a['name']:a for a in doc['animations']}
        require(set(asset['animations'])==set(clips),'Missing/foreign animation clips: '+str(set(clips)))
        for clip in clips.values():
            require(all(c['target']['node']==names[asset['opening']['node']] for c in clip['channels']),'Clip modifies unrelated nodes')
        require(len(doc['materials'])==3,'Three material budget')
        require(all('bufferView' in image and image.get('mimeType')=='image/png' for image in doc['images']),'Images must be embedded PNGs')
        require(all('baseColorTexture' in m['pbrMetallicRoughness'] for m in doc['materials']),'Missing painted PBR base color')
        require(not doc.get('extensionsRequired'),'Custom glTF extension required')
        triangles=0
        for mesh in doc['meshes']:
            for primitive in mesh['primitives']:
                require(primitive.get('mode',4)==4 and not primitive.get('targets'),'Rigid triangle surfaces required')
                require(not {'JOINTS_0','WEIGHTS_0'} & primitive['attributes'].keys(),'Unexpected skin attributes')
                triangles+=doc['accessors'][primitive['indices']]['count']//3
        require(triangles==asset['triangles'] and triangles<=5000,'Triangle count/budget mismatch')
    for texture in document['textures']:
        path=(folder/texture['file']).resolve()
        require(path.is_relative_to(folder),'Texture path escapes pack')
        require(hashlib.sha256(path.read_bytes()).hexdigest()==texture['sha256'],'Texture fingerprint mismatch')
    return document
