"""Create the complete portable Chamber prop delivery after its acceptance gates."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from chamber_props.validate import verify, require


def build(pack,output):
    pack=Path(pack).resolve();output=Path(output).resolve()
    document=verify(pack)
    files={}
    for asset in document['assets']:
        for name in (asset['file'],asset['source']['file']):files[name]=(pack/name).read_bytes()
        for state in ('closed','open'):
            name='previews/'+asset['id']+'-'+state+'.png'
            files[name]=(pack/name).read_bytes()
    for record in document['textures']:files[record['file']]=(pack/record['file']).read_bytes()
    for engine in ('blender','godot'):
        proof=json.loads((pack/(engine+'-validation.json')).read_text(encoding='utf-8'))
        require(proof['status']=='pass' and {a['id'] for a in proof['assets']}=={a['id'] for a in document['assets']},'Incomplete '+engine+' acceptance')
        require({a['id']:a['sha256'] for a in proof['assets']}=={a['id']:a['sha256'] for a in document['assets']},'Stale '+engine+' proof')
    for name in ('pack.json','collision-spec.json','blender-validation.json','godot-validation.json'):
        files[name]=(pack/name).read_bytes()
    files['README.md']=(ROOT/'example/v2/props/StytchChamberV1/README.md').read_bytes()
    files['LICENSE']=(ROOT/'LICENSE').read_bytes()
    files['scripts/author_stytch_chamber.py']=(ROOT/'scripts/author_stytch_chamber.py').read_bytes()
    files['scripts/run_chamber_godot.py']=(ROOT/'scripts/run_chamber_godot.py').read_bytes()
    for path in sorted((ROOT/'scripts/chamber_props').glob('*')):
        if path.suffix in ('.py','.gd'):files['scripts/chamber_props/'+path.name]=path.read_bytes()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):archive.writestr(name,data)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack',type=Path,default=ROOT/'example/v2/props/StytchChamberV1')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/stytch-chamber-v1.zip')
    args=parser.parse_args();print(build(args.pack,args.output))
