"""Offline immutable host-tool evidence packets, never quality certificates.

Hashes bind caller-observed records, not provider signatures. Preserve the
returned packet hash independently: a filesystem owner can replace an entire
self-consistent packet. No mtime cache participates in verification.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_ASSETS = 64
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
ROLES = frozenset(('before','reference','prompt','after','output','failure','raw_provenance','glb','mask'))


class ArchiveError(ValueError):
    """Malformed, unsafe, incomplete, changed or over-budget evidence."""


def _fields(value, required, optional=()):
    if type(value) is not dict or set(value)-set(required)-set(optional) or set(required)-set(value):
        raise ArchiveError('Unsupported or missing record fields.')


def _text(value, name, maximum=2048, *, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not str or not value.strip() or len(value)>maximum or '\0' in value:
        raise ArchiveError(f'{name} must be bounded nonempty text.')


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):
        raise ArchiveError('Expected a lowercase SHA-256 address.')
    return value


def _number(value, name, maximum=1e12):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=maximum:
        raise ArchiveError(f'{name} must be a bounded finite nonnegative number.')


def _json_bytes(value):
    nodes=0
    def visit(item,depth):
        nonlocal nodes
        nodes+=1
        if nodes>100000 or depth>32:
            raise ArchiveError('JSON structure budget exceeded.')
        if item is None or type(item) in (bool,str,int):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item: visit(child,depth+1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values(): visit(child,depth+1)
            return
        raise ArchiveError('Only finite JSON data is accepted.')
    visit(value,0)
    try:
        return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    except (UnicodeError,ValueError,OverflowError) as exc:
        raise ArchiveError('Invalid finite UTF-8 JSON.') from exc


def _json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ArchiveError('Duplicate JSON field.')
            result[key]=value
        return result
    def invalid(_): raise ArchiveError('Nonfinite JSON number.')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)
        _json_bytes(value)
        return value
    except (UnicodeError,ValueError,RecursionError,OverflowError) as exc:
        raise ArchiveError('Malformed or over-budget JSON.') from exc


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&0x400)


def _directory(path):
    path=Path(os.path.abspath(path))
    for current in reversed((path,*path.parents)):
        try: info=current.lstat()
        except FileNotFoundError: raise ArchiveError('Required directory is absent.') from None
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ArchiveError('Directory links and non-directories are not evidence roots.')
    return path


def _read(path, limit):
    path=Path(os.path.abspath(path))
    _directory(path.parent)
    try:
        before=path.lstat()
        if _linked(before) or not stat.S_ISREG(before.st_mode) or before.st_size>limit:
            raise ArchiveError('Evidence must be a bounded regular file, never a link.')
        flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
        descriptor=os.open(path,flags)
        with os.fdopen(descriptor,'rb') as stream:
            opened=os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino):
                raise ArchiveError('Evidence changed while opening.')
            raw=stream.read(limit+1)
            after=os.fstat(stream.fileno())
        current=path.lstat()
        if len(raw)>limit or len(raw)!=opened.st_size or _linked(current) or (
                opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(
                after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or (
                current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino):
            raise ArchiveError('Evidence changed during its snapshot.')
        return raw
    except OSError as exc:
        raise ArchiveError(f'Evidence cannot be read safely ({type(exc).__name__}).') from exc


def _relative(value):
    _text(value,'asset path',512)
    if '\\' in value or value.startswith('/'):
        raise ArchiveError('Asset paths must be portable relative POSIX paths.')
    parts=value.split('/')
    reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    if len(parts)>8 or any(p in ('','.','..') or p[-1:] in (' ','.') or any(ord(c)<32 or c in ':<>|?*' for c in p)
            or p.split('.')[0].upper() in reserved for p in parts):
        raise ArchiveError('Unsafe, ambiguous or over-deep asset path.')
    return value


def _time(value):
    _text(value,'UTC time',40)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z',value):
        raise ArchiveError('Times require explicit UTC date, time and Z suffix.')
    try: return datetime.fromisoformat(value[:-1]+'+00:00').astimezone(timezone.utc)
    except ValueError as exc: raise ArchiveError('Invalid UTC time.') from exc


def _execution(data):
    _fields(data,('mode','tool_name','request_id','backend_model','started_at','finished_at','latency_seconds',
        'outcome','error','max_calls','calls','billing_mode','cost','usage','parameters','raw_provenance_asset'))
    if data['mode']!='host_tool' or data['billing_mode']!='host_tool_no_api_invoice':
        raise ArchiveError('This archive profile accepts host-tool observations, never service API invoices.')
    for name in ('tool_name','raw_provenance_asset'): _text(data[name],name,256)
    for name in ('request_id','backend_model','error'): _text(data[name],name,4096,nullable=True)
    if type(data['max_calls']) is not int or data['max_calls']!=1 or type(data['calls']) is not int or data['calls'] not in (0,1):
        raise ArchiveError('The explicitly bounded trial permits at most one tool call.')
    if data['outcome'] not in ('completed','failed','cancelled','unknown'):
        raise ArchiveError('Unsupported technical outcome.')
    if data['outcome']=='completed' and data['calls']!=1:
        raise ArchiveError('A completed tool outcome requires one observed call.')
    if data['outcome']=='failed' and not data['error']:
        raise ArchiveError('A failed attempt requires its observed error.')
    elapsed=(_time(data['finished_at'])-_time(data['started_at'])).total_seconds()
    _number(data['latency_seconds'],'observed latency',86400)
    if elapsed<0 or elapsed>86400 or abs(elapsed-data['latency_seconds'])>max(1.1,elapsed*.02):
        raise ArchiveError('Observed latency is inconsistent with the recorded interval.')
    cost=data['cost']; _fields(cost,('status','amount','currency'))
    if cost['status']=='unknown':
        if cost['amount'] is not None or cost['currency'] is not None:
            raise ArchiveError('Unknown cost is null, never an inferred zero or currency.')
    elif cost['status']=='reported':
        _number(cost['amount'],'reported cost'); _text(cost['currency'],'reported currency',32)
    else: raise ArchiveError('Unsupported cost provenance.')
    usage=data['usage']; _fields(usage,('status','values'))
    if usage['status']=='unknown':
        if usage['values'] is not None: raise ArchiveError('Unknown usage requires null values.')
    elif usage['status']=='reported':
        if type(usage['values']) is not dict or not usage['values'] or len(usage['values'])>32:
            raise ArchiveError('Reported usage requires explicit bounded measurements.')
        for name,value in usage['values'].items():
            _text(name,'usage name',64); _number(value,'usage measurement')
    else: raise ArchiveError('Unsupported usage provenance.')
    if type(data['parameters']) is not dict or len(_json_bytes(data['parameters']))>65536:
        raise ArchiveError('Exposed parameters require a JSON object within 64 KiB.')


def _manifest(data):
    _fields(data,('schema_version','attempt_id','execution','assets'))
    if type(data['schema_version']) is not int or data['schema_version']!=1:
        raise ArchiveError('Unsupported manifest version.')
    if type(data['attempt_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,127}',data['attempt_id']):
        raise ArchiveError('Invalid attempt identifier.')
    _execution(data['execution'])
    if type(data['assets']) is not list or not 1<=len(data['assets'])<=MAX_ASSETS:
        raise ArchiveError('Asset count exceeds the bounded archive profile.')
    ids,paths,digests,total=set(),set(),{},0
    for asset in data['assets']:
        _fields(asset,('asset_id','role','path','sha256','bytes','media_type'))
        if type(asset['asset_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,127}',asset['asset_id']):
            raise ArchiveError('Invalid asset identifier.')
        path=_relative(asset['path']); digest=_sha(asset['sha256'])
        if asset['asset_id'] in ids or path.casefold() in paths:
            raise ArchiveError('Duplicate asset identity or portable path.')
        ids.add(asset['asset_id']); paths.add(path.casefold())
        if type(asset['role']) is not str or asset['role'] not in ROLES or type(asset['bytes']) is not int or not 0<=asset['bytes']<=MAX_ASSET_BYTES:
            raise ArchiveError('Asset role or byte budget is invalid.')
        _text(asset['media_type'],'media type',128)
        if digest in digests and digests[digest]!=asset['bytes']:
            raise ArchiveError('Duplicate content address has inconsistent size.')
        digests[digest]=asset['bytes']; total+=asset['bytes']
    if total>MAX_TOTAL_BYTES: raise ArchiveError('Aggregate artifact byte budget exceeded.')
    roles={role:[a for a in data['assets'] if a['role']==role] for role in ROLES}
    if not roles['before'] or not roles['reference'] or len(roles['prompt'])!=1 or len(roles['raw_provenance'])!=1:
        raise ArchiveError('Original, reference, exact prompt and raw observed provenance are required.')
    if roles['raw_provenance'][0]['asset_id']!=data['execution']['raw_provenance_asset']:
        raise ArchiveError('Raw provenance identity is detached from execution.')
    if data['execution']['outcome']=='completed' and not roles['after']:
        raise ArchiveError('A completed attempt requires its actual after artifact.')
    if data['execution']['outcome']=='failed' and not roles['failure']:
        raise ArchiveError('Failed attempts require retained failure evidence.')
    return roles


def _payloads(manifest,read):
    objects={}
    for asset in manifest['assets']:
        raw=read(asset)
        if len(raw)!=asset['bytes'] or hashlib.sha256(raw).hexdigest()!=asset['sha256']:
            raise ArchiveError('Asset content differs from its declared bytes or SHA-256.')
        objects[asset['sha256']]=raw
        if asset['role']=='prompt':
            try: prompt=raw.decode('utf-8')
            except UnicodeError as exc: raise ArchiveError('The exact prompt must be UTF-8 text.') from exc
            if not prompt.strip() or len(raw)>131072: raise ArchiveError('Exact prompt is empty or over budget.')
            exposed=manifest['execution']['parameters']
            if 'prompt' in exposed and exposed['prompt']!=prompt:
                raise ArchiveError('The retained prompt differs from the exposed exact tool argument.')
            if 'prompt_sha256' in exposed and exposed['prompt_sha256']!=asset['sha256']:
                raise ArchiveError('The retained prompt differs from the exposed prompt content address.')
        if asset['role']=='raw_provenance':
            observed=_json(raw)
            _fields(observed,('schema_version','execution'),('tool_response',))
            if type(observed['schema_version']) is not int or observed['schema_version']!=1 or observed['execution']!=manifest['execution']:
                raise ArchiveError('Raw caller-observed provenance was edited or disagrees with execution.')
    return objects


def _inventory(root,files):
    root=_directory(root)
    expected=set(files); allowed_dirs={''}
    for name in expected:
        allowed_dirs.update(str(p).replace('\\','/') for p in Path(name).parents if str(p)!='.')
    found=set(); count=0
    for current,directories,names in os.walk(root,followlinks=False):
        for name in [*directories,*names]:
            path=Path(current)/name; relative=path.relative_to(root).as_posix(); info=path.lstat(); count+=1
            if count>512 or _linked(info): raise ArchiveError('Unexpected links or excessive directory entries.')
            if stat.S_ISDIR(info.st_mode):
                if relative not in allowed_dirs: raise ArchiveError('Unlisted directory or cache evidence.')
            elif stat.S_ISREG(info.st_mode): found.add(relative)
            else: raise ArchiveError('Nonregular evidence is not accepted.')
    if found!=expected: raise ArchiveError('Packet contains missing or unlisted files; preserve every output and failure explicitly.')


def _publish(output,files,seal_name,seal):
    """Reserve an unused directory; the exclusive final seal commits the packet.

    A crash may retain an unsealed directory, which verification refuses. Never
    repair or reuse it in place. Existing accepted archives are never replaced.
    """
    output=Path(os.path.abspath(output)); _directory(output.parent)
    try: output.mkdir()
    except OSError as exc: raise ArchiveError('Archive destination must be a new directory.') from exc
    for name,raw in [*files.items(),(seal_name,seal)]:
        target=output/name
        target.parent.mkdir(parents=True,exist_ok=True)
        _directory(target.parent)
        with target.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        target.chmod(stat.S_IREAD|stat.S_IRGRP|stat.S_IROTH)
        if os.name!='nt':
            descriptor=os.open(target.parent,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    return output


def import_attempt(source: Path, output: Path) -> dict:
    """Snapshot a closed local manifest/asset directory without executing tools."""
    source=Path(os.path.abspath(source)); _directory(source.parent)
    if Path(os.path.abspath(output)).is_relative_to(source.parent):
        raise ArchiveError('An archive destination must be separate from its immutable source packet.')
    raw=_read(source,MAX_MANIFEST_BYTES); manifest=_json(raw); _manifest(manifest)
    if source.name.casefold() in {a['path'].casefold() for a in manifest['assets']}:
        raise ArchiveError('The source manifest cannot also be an asset.')
    _inventory(source.parent,{source.name,*(a['path'] for a in manifest['assets'])})
    objects=_payloads(manifest,lambda a:_read(source.parent/a['path'],MAX_ASSET_BYTES))
    # Detect source replacement even when an editor restores file timestamps.
    if _read(source,MAX_MANIFEST_BYTES)!=raw:
        raise ArchiveError('Source manifest changed during collection.')
    for asset in manifest['assets']:
        if _read(source.parent/asset['path'],MAX_ASSET_BYTES)!=objects[asset['sha256']]:
            raise ArchiveError('Source asset changed during collection.')
    _inventory(source.parent,{source.name,*(a['path'] for a in manifest['assets'])})
    packet=_json_bytes(dict(schema_version=1,kind='meshvenn.host_tool_attempt',source_manifest_sha256=hashlib.sha256(raw).hexdigest(),
        source_manifest_bytes=len(raw),manifest=manifest))
    digest=hashlib.sha256(packet).hexdigest()
    _publish(output,{'packet.json':packet,'source-manifest.json':raw,**{'objects/'+sha:data for sha,data in objects.items()}},
        'packet.sha256',(digest+'\n').encode('ascii'))
    return verify_archive(output)


def verify_archive(path: Path) -> dict:
    """Re-read every sealed byte; integrity does not certify visual fidelity."""
    path=_directory(path)
    raw=_read(path/'packet.json',MAX_MANIFEST_BYTES*2); packet=_json(raw)
    _fields(packet,('schema_version','kind','source_manifest_sha256','source_manifest_bytes','manifest'))
    if type(packet['schema_version']) is not int or packet['schema_version']!=1 or packet['kind']!='meshvenn.host_tool_attempt' or _json_bytes(packet)!=raw:
        raise ArchiveError('Unsupported or noncanonical archive packet.')
    digest=hashlib.sha256(raw).hexdigest()
    if _read(path/'packet.sha256',65)!=(digest+'\n').encode('ascii'):
        raise ArchiveError('Packet seal does not match its exact bytes.')
    source=_read(path/'source-manifest.json',MAX_MANIFEST_BYTES)
    if len(source)!=packet['source_manifest_bytes'] or hashlib.sha256(source).hexdigest()!=_sha(packet['source_manifest_sha256']) or _json(source)!=packet['manifest']:
        raise ArchiveError('Original manifest bytes were changed.')
    manifest=packet['manifest']; roles=_manifest(manifest)
    _inventory(path,{'packet.json','packet.sha256','source-manifest.json',*('objects/'+a['sha256'] for a in manifest['assets'])})
    _payloads(manifest,lambda a:_read(path/'objects'/a['sha256'],MAX_ASSET_BYTES))
    return dict(schema_version=1,integrity_status='verified',packet_sha256=digest,attempt_id=manifest['attempt_id'],
        execution=manifest['execution'],assets=manifest['assets'],roles={role:[a['sha256'] for a in assets] for role,assets in sorted(roles.items())},
        verification_status='unknown',semantic_status='unknown',human_review_status='unknown',delivery_status='unknown',
        provenance_authority='caller_observed_not_provider_attested',limits=dict(max_calls=1,max_assets=MAX_ASSETS,
            max_asset_bytes=MAX_ASSET_BYTES,max_total_bytes=MAX_TOTAL_BYTES))
