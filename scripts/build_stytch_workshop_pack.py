"""Package the editable module collection and its independent Godot asset adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PACK=ROOT/'example/v2/modules/StytchWorkshopV1'
TOOLS=ROOT/'extensions/meshvenn_sketch/examples/stytch_workshop'


def build(destination=None,pack=PACK):
    destination=Path(destination or ROOT/'dist/stytch-workshop-modules-v1.zip')
    if destination.exists():raise FileExistsError('Choose a new ZIP output')
    doc=json.loads((pack/'pack.json').read_text())
    files={}
    for module in doc['modules']:
        if 'runtime_scene' not in module:raise ValueError('Compile verified Godot runtime scenes before packaging')
        if module['runtime_scene']['source_sha256']!=module['skinned']['sha256']:raise ValueError('Runtime scene is stale')
        for kind in ('skinned','attachment','runtime_scene'):
            if kind not in module:continue
            record=module[kind];name=record['file'];path=(pack/name).resolve()
            if not path.is_relative_to(pack.resolve()):raise ValueError('Asset path escapes the pack')
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Stale module GLB: '+name)
            files[name]=data
    for name in ('source.blend','pack.json','validation.json','godot-validation.json'):
        files[name]=(pack/name).read_bytes()
    previews=list((pack/'previews').glob('*.png'))
    if {p.stem for p in previews}!={'equipment','replacements','accessories','accessories-back','complete','articulated'}:
        raise ValueError('All six module previews are required')
    for path in previews:files['previews/'+path.name]=path.read_bytes()
    files['README.md']=(PACK/'README.md').read_text(encoding='utf-8').encode()
    files['LICENSE']=(ROOT/'LICENSE').read_text(encoding='utf-8').encode()
    files['godot_module_adapter.gd']=(TOOLS/'godot_module_adapter.gd').read_text(encoding='utf-8').encode()
    files['compile_runtime.gd']=(TOOLS/'compile_runtime.gd').read_text(encoding='utf-8').encode()
    for path in TOOLS.glob('*.py'):files['Source/'+path.name]=path.read_text(encoding='utf-8').encode()
    if len(files)<29 or len(doc['modules'])!=10:raise ValueError('Module delivery is incomplete')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staged=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.zip',delete=False) as stream:staged=Path(stream.name)
        with zipfile.ZipFile(staged,'w') as archive:
            for name,data in sorted(files.items()):
                info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                info.create_system=3;info.external_attr=0o100644<<16;archive.writestr(info,data)
        os.link(staged,destination)
    finally:
        if staged is not None:staged.unlink(missing_ok=True)
    return destination


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path);parser.add_argument('--pack',type=Path,default=PACK)
    args=parser.parse_args();print(build(args.output,args.pack).resolve())
