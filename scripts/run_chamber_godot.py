"""Run real importer and rigid-prop acceptance in a clean disposable Godot project."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from chamber_props.validate import verify


def run(godot,pack,output):
    pack=Path(pack).resolve();output=Path(output).resolve()
    verify(pack)
    output.mkdir(parents=True,exist_ok=False)
    (output/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Chamber rigid prop acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
    (output/'assets').mkdir()
    for path in pack.glob('*.glb'):shutil.copy2(path,output/'assets'/path.name)
    shutil.copy2(pack/'pack.json',output/'assets/pack.json')
    shutil.copy2(ROOT/'scripts/chamber_props/godot_smoke.gd',output/'godot_smoke.gd')
    for name,extra in (('import',['--editor','--import']),('acceptance',['--script','res://godot_smoke.gd'])):
        result=subprocess.run([str(godot),'--headless','--path',str(output),*extra],capture_output=True,text=True,timeout=120)
        log=result.stdout+'\n'+result.stderr
        (output/(name+'.log')).write_text(log,encoding='utf-8')
        print(log)
        if result.returncode or any(marker in log for marker in ('SCRIPT ERROR','ERROR:','Parse Error')):
            raise RuntimeError(f'Godot {name} failed')
    proof=json.loads((output/'validation.json').read_text())
    if proof['status']!='pass' or len(proof['assets'])!=2:raise ValueError('Incomplete Godot proof')
    shutil.copy2(output/'validation.json',pack/'godot-validation.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--pack',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.godot,args.pack,args.output)
