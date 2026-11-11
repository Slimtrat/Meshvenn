"""Validate, compile and exercise modules through Godot's official PCK exporter."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from prepare_workshop_godot import prepare

ERROR=re.compile(r'(?im)(?:^|\n)(?:ERROR:|SCRIPT ERROR:)|Broken external resource|invalid UID|Can.t load dependency')


def run(godot,pack,output):
    pack=pack.resolve();output=output.resolve();godot=godot.resolve()
    if godot.name.endswith('_console.exe'):
        direct=godot.with_name(godot.name.replace('_console.exe','.exe'))
        if direct.is_file():godot=direct  # Kill the actual engine on timeout, not its Windows console wrapper.
    project=prepare(pack,output/'project')
    def stage(name,args,marker=None,cwd=project,timeout=120,expected_exit=0):
        try:
            result=subprocess.run([str(godot),'--headless',*map(str,args)],cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'{name} exceeded {timeout}s') from exc
        log=result.stdout+'\n'+result.stderr
        (output/(name+'.log')).write_text(log,encoding='utf-8')
        clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',log)
        if result.returncode!=expected_exit or ERROR.search(clean) or (marker and marker not in clean):
            raise RuntimeError(f'{name} failed; see {output/(name+".log")}\n{log[-2000:]}')
        print(name+': PASS',flush=True)
        return clean
    stage('import',['--path',project,'--editor','--import'])
    stage('compile',['--path',project,'--script','compile_runtime.gd'],'WORKSHOP COMPILE PASS')
    # Only runtime records are produced by Godot; preserve every original frame,
    # number, owner and input fingerprint in the portable authoring manifest.
    original=json.loads((pack/'pack.json').read_text(encoding='utf-8'))
    compiled=json.loads((project/'pack.json').read_text(encoding='utf-8'))
    records={m['id']:m['runtime_scene'] for m in compiled['modules']}
    for module in original['modules']:module['runtime_scene']=records[module['id']]
    (project/'pack.json').write_text(json.dumps(original,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    stage('native',['--path',project,'--script','check.gd'],'WORKSHOP GODOT PASS')
    stage('cache',['--path',project,'--script','cache_check.gd'],'WORKSHOP CACHE PASS: 9 ')
    # A valid raw GLB and manifest changed without reimport must never stamp the
    # old imported mesh with the new source hash. All mutations are disposable.
    first=original['modules'][0];source=project/first['skinned']['file']
    raw=source.read_bytes();manifest_bytes=(project/'pack.json').read_bytes()
    changed=bytearray(raw);key=changed.index(b'"generator"');value=changed.index(b':',key)+1
    value=changed.index(b'"',value)+1;changed[value]=ord('X') if changed[value]!=ord('X') else ord('Y')
    try:
        source.write_bytes(changed)
        probe=json.loads(manifest_bytes);probe['modules'][0]['skinned']['sha256']=hashlib.sha256(changed).hexdigest()
        (project/'pack.json').write_text(json.dumps(probe),encoding='utf-8')
        stage('stale_import',['--path',project,'--script','compile_runtime.gd'],
              'WORKSHOP COMPILE FAIL: imported scene is stale',expected_exit=1)
    finally:
        source.write_bytes(raw);(project/'pack.json').write_bytes(manifest_bytes)
    imported_config=(source.with_suffix(source.suffix+'.import')).read_text(encoding='utf-8')
    imported_path=re.search(r'(?m)^path="(res://[^"]+)"',imported_config).group(1)
    imported=project/imported_path.removeprefix('res://');imported_bytes=imported.read_bytes()
    changed=bytearray(imported_bytes);changed[-1]^=1
    try:
        imported.write_bytes(changed)
        stage('tampered_import',['--path',project,'--script','compile_runtime.gd'],
              'WORKSHOP COMPILE FAIL: imported scene is stale',expected_exit=1)
    finally:imported.write_bytes(imported_bytes)
    pck=output/'workshop-runtime.pck'
    stage('export',['--path',project,'--export-pack','Module acceptance',pck],timeout=180)
    isolated=output/'runtime-only';isolated.mkdir()
    stage('runtime',['--main-pack',pck,'--script','res://runtime_check.gd','--',project/'godot-validation.json'],
          'WORKSHOP SOURCE-FREE PCK PASS',cwd=isolated)
    # This same release-mode script must fail promptly, without PASS, when a
    # compiled fingerprint is stale. Assertions may be disabled in a real game.
    report_path=project/'godot-validation.json'
    previous_report=report_path.read_bytes()
    failed=stage('runtime_negative',['--main-pack',pck,'--script','res://runtime_check.gd','--',report_path,'--negative-cache'],
        'WORKSHOP RUNTIME FAIL: Compiled module fingerprint changed',cwd=isolated,expected_exit=1)
    if 'WORKSHOP SOURCE-FREE PCK PASS' in failed or report_path.read_bytes()!=previous_report:
        raise RuntimeError('Failed runtime emitted success or replaced its proof report')
    report=json.loads(report_path.read_text(encoding='utf-8'))
    report.update(runtime_cache_rejections=9,stale_import_rejected=True,tampered_import_rejected=True,runtime_failure_exit_verified=True)
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(project/'pack.json',pack/'pack.json')
    shutil.copy2(project/'godot-validation.json',pack/'godot-validation.json')
    shutil.copytree(project/'runtime',pack/'runtime',dirs_exist_ok=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot',type=Path,required=True);parser.add_argument('--pack',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(run(args.godot,args.pack,args.output))
