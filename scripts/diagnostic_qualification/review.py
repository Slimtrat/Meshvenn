"""Human review records bound to exact packets, separately from asset approval.

The caller records who submitted a review. This module never infers a human
from an agent's labels, authenticates a person's identity or certifies delivery.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from .archive import (ArchiveError, MAX_MANIFEST_BYTES, _fields, _inventory, _json, _json_bytes,
                      _publish, _read, _sha, _text, _time, verify_archive)


def _review(data, packet):
    _fields(data,('schema_version','review_id','packet_sha256','scope','image_sha256s','glb_sha256s',
        'reviewer','state','reviewed_at','tasks','limitations'))
    if type(data['schema_version']) is not int or data['schema_version']!=1:
        raise ArchiveError('Unsupported review schema.')
    if type(data['review_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,127}',data['review_id']):
        raise ArchiveError('Invalid review identifier.')
    if _sha(data['packet_sha256'])!=packet['packet_sha256']:
        raise ArchiveError('The review belongs to different exact packet bytes.')
    if data['scope'] not in ('image_review','full_delivery') or data['state'] not in ('pending','submitted'):
        raise ArchiveError('Invalid review scope or submission state.')
    assets=packet['assets']; all_hashes={a['sha256'] for a in assets}
    images={a['sha256'] for a in assets if a['role'] in ('after','output') and a['media_type'].startswith('image/')}
    glbs={a['sha256'] for a in assets if a['role']=='glb'}
    for name,allowed in (('image_sha256s',images),('glb_sha256s',glbs)):
        values=data[name]
        if type(values) is not list or len(values)>64 or any(type(value) is not str for value in values) or len(set(values))!=len(values):
            raise ArchiveError('Review subjects require unique bounded SHA-256 lists.')
        if not set(values)<=allowed or any(_sha(value) not in allowed for value in values):
            raise ArchiveError('A review subject is absent from the exact packet or has a different role.')
    reviewer=data['reviewer']; _fields(reviewer,('kind','name','experience','non_3d','attested'))
    if reviewer['kind'] not in ('human','agent','unknown') or reviewer['experience'] not in ('none','basic','experienced'):
        raise ArchiveError('The reviewer source and declared experience must be explicit.')
    _text(reviewer['name'],'reviewer name',256,nullable=True)
    if type(reviewer['non_3d']) is not bool or type(reviewer['attested']) is not bool:
        raise ArchiveError('Reviewer background and attestation require explicit booleans.')
    if data['reviewed_at'] is not None: _time(data['reviewed_at'])
    if data['state']=='pending' and (reviewer['attested'] or data['reviewed_at'] is not None):
        raise ArchiveError('Pending review cannot carry a completed attestation.')
    if type(data['tasks']) is not list or len(data['tasks'])>32:
        raise ArchiveError('Review tasks exceed their bounded profile.')
    ids=set()
    for task in data['tasks']:
        _fields(task,('task_id','question','result','evidence_refs','notes'))
        _text(task['task_id'],'task ID',128); _text(task['question'],'review question',2048)
        if task['task_id'] in ids: raise ArchiveError('Duplicate review task.')
        ids.add(task['task_id'])
        if task['result'] not in ('pass','fail','unknown','not_reviewed'):
            raise ArchiveError('Review answers require explicit outcomes, including unknown.')
        refs=task['evidence_refs']
        if type(refs) is not list or len(refs)>64 or any(type(ref) is not str for ref in refs) or len(set(refs))!=len(refs):
            raise ArchiveError('Review evidence references must be unique bounded SHA-256 lists.')
        if not set(refs)<=all_hashes or any(_sha(ref) not in all_hashes for ref in refs):
            raise ArchiveError('Review task evidence is absent from this exact packet.')
        if type(task['notes']) is not str or len(task['notes'])>4096:
            raise ArchiveError('Review notes exceed their text budget.')
    if type(data['limitations']) is not list or not 1<=len(data['limitations'])<=32:
        raise ArchiveError('Declared review limitations are required.')
    for limitation in data['limitations']: _text(limitation,'review limitation',2048)
    return images


def _assessment(data, packet):
    images=_review(data,packet)
    reasons=[]; reviewer=data['reviewer']
    if data['state']!='submitted': reasons.append('Human review is pending.')
    if reviewer['kind']!='human': reasons.append('No explicitly human submission was recorded; agent labels do not qualify.')
    if not reviewer['attested'] or reviewer['name'] is None or data['reviewed_at'] is None:
        reasons.append('The reviewer has not personally attested a named, dated submission.')
    if len(data['tasks'])<3: reasons.append('At least three explicit review tasks are required.')
    if not data['image_sha256s']: reasons.append('No exact generated image was reviewed.')
    if images-set(data['image_sha256s']): reasons.append('Some output images have not been reviewed.')
    if any(task['result'] in ('unknown','not_reviewed') or not task['evidence_refs'] for task in data['tasks']):
        reasons.append('Review answers or their exact evidence remain unresolved.')
    subjects=set(data['image_sha256s'])|set(data['glb_sha256s'])
    if any(task['result'] in ('pass','fail') and not subjects.intersection(task['evidence_refs']) for task in data['tasks']):
        reasons.append('A task outcome is not bound to any selected reviewed image or GLB.')
    if data['scope']=='full_delivery':
        reasons.append('A review record alone cannot qualify full 3D delivery or replace its independent acceptance evidence.')
    status='unknown' if reasons else 'fail' if any(task['result']=='fail' for task in data['tasks']) else 'pass'
    return dict(schema_version=1,packet_sha256=packet['packet_sha256'],review_id=data['review_id'],scope=data['scope'],
        image_sha256s=data['image_sha256s'],glb_sha256s=data['glb_sha256s'],state=data['state'],reviewed_at=data['reviewed_at'],
        human_review_status=status,verification_status='unknown',delivery_status='unknown',reasons=reasons,
        reviewer=data['reviewer'],tasks=data['tasks'],limitations=data['limitations'],
        review_authority='caller_recorded_human_attestation_not_identity_authentication')


def import_review(source: Path, archive: Path, output: Path) -> dict:
    """Seal an explicit submitted/pending review without modifying its packet."""
    packet=verify_archive(archive); raw=_read(source,MAX_MANIFEST_BYTES); data=_json(raw)
    if Path(os.path.abspath(output)).is_relative_to(Path(os.path.abspath(archive))):
        raise ArchiveError('Human reviews must be stored separately from the sealed evidence packet.')
    _review(data,packet)
    if _read(source,MAX_MANIFEST_BYTES)!=raw:
        raise ArchiveError('Review provenance changed during collection.')
    sealed=_json_bytes(dict(schema_version=1,kind='meshvenn.exact_packet_review',review=data,
        source_review_sha256=hashlib.sha256(raw).hexdigest(),source_review_bytes=len(raw)))
    digest=hashlib.sha256(sealed).hexdigest()
    _publish(output,{'review.json':sealed,'source-review.json':raw},'review.sha256',(digest+'\n').encode('ascii'))
    return verify_review(output,archive)


def verify_review(path: Path, archive: Path) -> dict:
    """Re-read the original review and bind it to current verified packet bytes."""
    packet=verify_archive(archive); path=Path(path)
    _inventory(path,{'review.json','source-review.json','review.sha256'})
    raw=_read(path/'review.json',MAX_MANIFEST_BYTES*2); sealed=_json(raw)
    _fields(sealed,('schema_version','kind','review','source_review_sha256','source_review_bytes'))
    if type(sealed['schema_version']) is not int or sealed['schema_version']!=1 or sealed['kind']!='meshvenn.exact_packet_review' or _json_bytes(sealed)!=raw:
        raise ArchiveError('Invalid or noncanonical review archive.')
    digest=hashlib.sha256(raw).hexdigest()
    if _read(path/'review.sha256',65)!=(digest+'\n').encode('ascii'):
        raise ArchiveError('Review seal does not match its exact bytes.')
    original=_read(path/'source-review.json',MAX_MANIFEST_BYTES)
    if len(original)!=sealed['source_review_bytes'] or hashlib.sha256(original).hexdigest()!=_sha(sealed['source_review_sha256']) or _json(original)!=sealed['review']:
        raise ArchiveError('Original human/agent review provenance was edited.')
    result=_assessment(sealed['review'],packet)
    result.update(integrity_status='verified',review_sha256=digest,source_review_sha256=sealed['source_review_sha256'])
    return result


def review_status(archive: Path, review: Path | None = None) -> dict:
    if review is not None: return verify_review(review,archive)
    packet=verify_archive(archive)
    return dict(schema_version=1,packet_sha256=packet['packet_sha256'],human_review_status='unknown',
        verification_status='unknown',delivery_status='unknown',reasons=['No human review has been supplied.'])
