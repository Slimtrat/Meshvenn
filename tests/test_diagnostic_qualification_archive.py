"""Archive/review mechanics only; these fixtures do not qualify provider fidelity."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from scripts.diagnostic_qualification import archive, review


def png(color):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,2,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(color)*2)*2))+chunk(b'IEND',b'')


def source(root, *, outcome='completed'):
    root.mkdir(); (root/'assets').mkdir()
    execution=dict(mode='host_tool',tool_name='fixture.only',request_id=None,backend_model=None,
        started_at='2026-11-16T10:00:00Z',finished_at='2026-11-16T10:00:02Z',latency_seconds=2.,
        outcome=outcome,error='Observed fixture error' if outcome=='failed' else None,max_calls=1,calls=1,
        billing_mode='host_tool_no_api_invoice',cost=dict(status='unknown',amount=None,currency=None),
        usage=dict(status='unknown',values=None),parameters={'prompt':'Change only the badge.'},raw_provenance_asset='raw')
    records=[('before','before','before.png','image/png',png((20,50,100,255))),
        ('reference','reference','reference.png','image/png',png((20,50,100,255))),
        ('prompt','prompt','prompt.txt','text/plain',b'Change only the badge.'),
        ('raw','raw_provenance','raw.json','application/json',json.dumps(dict(schema_version=1,execution=execution,tool_response={'fixture':True})).encode())]
    if outcome=='completed': records.append(('after','after','after.png','image/png',png((100,50,20,255))))
    if outcome=='failed': records.append(('failure','failure','failure.txt','text/plain',b'Observed fixture error'))
    assets=[]
    for identity,role,name,media,raw in records:
        path='assets/'+name; (root/path).write_bytes(raw)
        assets.append(dict(asset_id=identity,role=role,path=path,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),media_type=media))
    manifest=dict(schema_version=1,attempt_id='fixture-trial',execution=execution,assets=assets)
    path=root/'attempt.json'; path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return path,manifest


def human_record(packet, *, kind='human', state='submitted'):
    after=packet['roles']['after'][0]
    return dict(schema_version=1,review_id='explicit-review',packet_sha256=packet['packet_sha256'],scope='image_review',
        image_sha256s=[after],glb_sha256s=[],reviewer=dict(kind=kind,name='Named reviewer' if state=='submitted' else None,
            experience='none',non_3d=True,attested=state=='submitted'),state=state,
        reviewed_at='2026-11-16T11:00:00Z' if state=='submitted' else None,
        tasks=[dict(task_id='task-'+str(i),question='Explicit visual review question '+str(i),
            result='pass' if state=='submitted' else 'not_reviewed',evidence_refs=[after],notes='Explicit answer, no 3D claim.') for i in range(3)],
        limitations=['Reviewer is not a 3D professional; no corrected GLB or D8 delivery evidence was reviewed.'])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)

    def test_completed_trial_preserves_exact_bytes_unknown_cost_and_deduplicates_only_content(self):
        manifest,data=source(self.root/'source'); raw=manifest.read_bytes()
        result=archive.import_attempt(manifest,self.root/'archive')
        self.assertEqual(result,archive.verify_archive(self.root/'archive'))
        self.assertEqual(result['execution']['cost'],dict(status='unknown',amount=None,currency=None))
        self.assertIsNone(result['execution']['usage']['values'])
        self.assertEqual(result['verification_status'],'unknown')
        self.assertEqual(result['delivery_status'],'unknown')
        self.assertEqual((self.root/'archive/source-manifest.json').read_bytes(),raw)
        self.assertEqual(len(list((self.root/'archive/objects').iterdir())),4)
        for asset in data['assets']:
            self.assertEqual((self.root/'archive/objects'/asset['sha256']).read_bytes(),(manifest.parent/asset['path']).read_bytes())
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'archive')
        self.assertEqual(archive.verify_archive(self.root/'archive'),result)

    def test_failed_trial_retains_failure_without_creating_an_after_success(self):
        manifest,_=source(self.root/'source',outcome='failed')
        result=archive.import_attempt(manifest,self.root/'archive')
        self.assertEqual(result['execution']['outcome'],'failed')
        self.assertEqual(result['roles']['after'],[])
        self.assertEqual(len(result['roles']['failure']),1)
        self.assertEqual(result['semantic_status'],'unknown')

    def test_prompt_binding_and_separate_destination_are_enforced(self):
        manifest,data=source(self.root/'source')
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,manifest.parent/'archive')
        prompt=next(a for a in data['assets'] if a['role']=='prompt')
        raw=b'Different prompt kept after the tool call.'; (manifest.parent/prompt['path']).write_bytes(raw)
        prompt.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)); manifest.write_text(json.dumps(data))
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'archive')

    def test_edit_with_restored_mtime_is_detected_without_cached_verification(self):
        manifest,_=source(self.root/'source'); result=archive.import_attempt(manifest,self.root/'archive')
        target=self.root/'archive/objects'/result['roles']['after'][0]; info=target.stat()
        target.chmod(stat.S_IWRITE|stat.S_IREAD); data=target.read_bytes(); target.write_bytes(bytes([data[0]^1])+data[1:])
        os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns))
        with self.assertRaises(archive.ArchiveError): archive.verify_archive(self.root/'archive')

    def test_source_mutation_after_first_read_is_detected_before_publication(self):
        manifest,data=source(self.root/'source'); target=manifest.parent/data['assets'][0]['path']; original=archive._read; changed=False
        def reading(path,limit):
            nonlocal changed
            raw=original(path,limit)
            if Path(path)==target and not changed:
                changed=True; info=target.stat(); target.write_bytes(bytes([raw[0]^1])+raw[1:]); os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns))
            return raw
        with patch.object(archive,'_read',side_effect=reading),self.assertRaises(archive.ArchiveError):
            archive.import_attempt(manifest,self.root/'archive')
        self.assertFalse((self.root/'archive').exists())

    def test_raw_provenance_disagreement_is_rejected_even_with_updated_asset_hash(self):
        manifest,data=source(self.root/'source'); raw_asset=next(a for a in data['assets'] if a['role']=='raw_provenance')
        observed=json.loads((manifest.parent/raw_asset['path']).read_text()); observed['execution']['backend_model']='invented-model'
        raw=json.dumps(observed).encode(); (manifest.parent/raw_asset['path']).write_bytes(raw)
        raw_asset.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)); manifest.write_text(json.dumps(data))
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'archive')

    def test_traversal_duplicate_fields_unknown_zero_usage_budget_and_unlisted_outputs_reject(self):
        alterations=(lambda d:d['assets'][0].update(path='../outside.png'),
            lambda d:d['assets'].append(copy.deepcopy(d['assets'][0])),
            lambda d:d['assets'][0].update(bytes=archive.MAX_ASSET_BYTES+1),
            lambda d:d['execution']['cost'].update(amount=0),
            lambda d:d['execution']['usage'].update(values={'images':0}),
            lambda d:d['execution'].update(calls=True),lambda d:d['execution'].update(latency_seconds=100),
            lambda d:d['execution'].update(started_at='2026-11-16Z'))
        for number,alter in enumerate(alterations):
            with self.subTest(number=number):
                manifest,data=source(self.root/('source-'+str(number))); alter(data); manifest.write_text(json.dumps(data))
                with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/('archive-'+str(number)))
        for number,raw in enumerate((b'{"schema_version":1,"schema_version":1}',b'{"value":NaN}',b'{"value":1e999}')):
            manifest,_=source(self.root/('json-'+str(number))); manifest.write_bytes(raw)
            with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/('bad-json-'+str(number)))
        manifest,_=source(self.root/'extra'); (manifest.parent/'cache.tmp').write_bytes(b'unlisted failure')
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'extra-archive')

    def test_symlink_asset_is_rejected_without_following_it(self):
        manifest,data=source(self.root/'source'); target=manifest.parent/data['assets'][0]['path']; outside=self.root/'outside.png'
        outside.write_bytes(target.read_bytes()); target.unlink()
        try: target.symlink_to(outside)
        except OSError as exc: self.skipTest('Host does not grant symlink creation: '+str(exc))
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'archive')

    @unittest.skipUnless(hasattr(os,'mkfifo'),'FIFO requires POSIX')
    def test_fifo_asset_is_rejected_before_a_blocking_open(self):
        manifest,data=source(self.root/'source'); target=manifest.parent/data['assets'][0]['path']; target.unlink(); os.mkfifo(target)
        with self.assertRaises(archive.ArchiveError): archive.import_attempt(manifest,self.root/'archive')


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup); self.root=Path(self.temporary.name)
        manifest,_=source(self.root/'source'); self.packet=archive.import_attempt(manifest,self.root/'archive')

    def record(self,data,name='review'):
        path=self.root/(name+'.json'); path.write_text(json.dumps(data),encoding='utf-8')
        return review.import_review(path,self.root/'archive',self.root/name)

    def test_explicit_human_image_review_never_certifies_delivery(self):
        result=self.record(human_record(self.packet))
        self.assertEqual(result['human_review_status'],'pass')
        self.assertEqual(result['scope'],'image_review')
        self.assertEqual(result['verification_status'],'unknown'); self.assertEqual(result['delivery_status'],'unknown')
        self.assertTrue(result['reviewer']['non_3d'])
        self.assertEqual(result,review.verify_review(self.root/'review',self.root/'archive'))

    def test_absent_pending_agent_unattested_and_incomplete_reviews_remain_unknown(self):
        self.assertEqual(review.review_status(self.root/'archive')['human_review_status'],'unknown')
        records=[human_record(self.packet,state='pending'),human_record(self.packet,kind='agent'),human_record(self.packet),human_record(self.packet)]
        records[2]['reviewer']['attested']=False; records[3]['tasks']=records[3]['tasks'][:1]
        for number,data in enumerate(records):
            self.assertEqual(self.record(data,'review-'+str(number))['human_review_status'],'unknown')

    def test_exact_packet_and_image_evidence_bindings_are_required(self):
        for number,field in enumerate(('packet_sha256','image_sha256s','task')):
            data=human_record(self.packet)
            if field=='packet_sha256': data[field]='f'*64
            elif field=='image_sha256s': data[field]=['f'*64]
            else: data['tasks'][0]['evidence_refs']=['f'*64]
            with self.assertRaises(archive.ArchiveError): self.record(data,'review-'+str(number))

    def test_full_delivery_and_unreviewed_output_cannot_be_promoted(self):
        data=human_record(self.packet); data['scope']='full_delivery'
        self.assertEqual(self.record(data)['human_review_status'],'unknown')

    def test_evidence_without_a_reviewed_subject_and_nested_review_destination_are_refused(self):
        data=human_record(self.packet)
        for task in data['tasks']: task['evidence_refs']=self.packet['roles']['before']
        self.assertEqual(self.record(data)['human_review_status'],'unknown')
        source_file=self.root/'other.json'; source_file.write_text(json.dumps(human_record(self.packet)))
        with self.assertRaises(archive.ArchiveError):
            review.import_review(source_file,self.root/'archive',self.root/'source/../archive/nested-review')
        self.assertEqual(archive.verify_archive(self.root/'archive')['packet_sha256'],self.packet['packet_sha256'])

    def test_original_review_bytes_are_not_replaced_or_cached(self):
        self.record(human_record(self.packet)); path=self.root/'review/source-review.json'; info=path.stat()
        path.chmod(stat.S_IWRITE|stat.S_IREAD); raw=path.read_bytes(); path.write_bytes(raw.replace(b'Named reviewer',b'Faked reviewer'))
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        with self.assertRaises(archive.ArchiveError): review.verify_review(self.root/'review',self.root/'archive')


if __name__=='__main__': unittest.main()
