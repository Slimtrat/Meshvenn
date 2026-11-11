"""Prepare a disposable Godot project to test the public module delivery."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=ROOT/'extensions/meshvenn_sketch/examples/stytch_workshop'


def prepare(pack,output):
    if output.exists():raise FileExistsError('Choose a fresh Godot test directory')
    output.mkdir(parents=True)
    (output/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Meshvenn module acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    shutil.copy2(pack/'pack.json',output/'pack.json')
    shutil.copytree(pack/'skinned',output/'skinned');shutil.copytree(pack/'attachments',output/'attachments')
    shutil.copy2(ROOT/'example/v2/modular/StytchDollDistalChains/character.glb',output/'reference.glb')
    shutil.copy2(EXAMPLES/'godot_module_adapter.gd',output/'godot_module_adapter.gd')
    shutil.copy2(ROOT/'extensions/meshvenn_sketch/tests/godot_workshop_smoke.gd',output/'check.gd')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(prepare(args.pack,args.output))
