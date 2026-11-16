"""Independent preservation/binding guards; no provider request or quality claim."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from scripts.appearance_diagnostic_corpus.authoring import png_rgba
from scripts.diagnostic_qualification.archive import import_attempt, verify_archive
from scripts.diagnostic_qualification.measure import compare_images

ROOT = Path(__file__).resolve().parents[1]
ATTEMPT = ROOT / 'tests/fixtures/diagnostics/provider-attempt-v1'
FROZEN_PACKET = '5c01bd5b596b017fe279d4da1b5ec89cc73a953919763f8efc9cc1acb7cafee8'


class IndependentEvidenceGuards(unittest.TestCase):
    def test_opaque_black_white_mask_does_not_hide_a_deleted_protected_part(self):
        # Authored PNG masks encode black/white support with opaque alpha.
        # Pixel zero is the badge; pixel one is an independently protected part.
        with tempfile.TemporaryDirectory(prefix='qualification-mask-guard-') as temporary:
            folder = Path(temporary)
            images = {
                'healthy': ((20, 90, 210, 255), (0, 0, 0, 255)),
                'before': ((230, 15, 45, 255), (0, 0, 0, 255)),
                'after': ((20, 90, 210, 255), (0, 0, 0, 0)),
                'mask': ((255, 255, 255, 255), (0, 0, 0, 255)),
            }
            paths = {}
            for name, pixels in images.items():
                paths[name] = folder / (name + '.png')
                paths[name].write_bytes(png_rgba(2, 1, bytes(channel for pixel in pixels for channel in pixel)))
            original = {name: path.read_bytes() for name, path in paths.items()}
            result = compare_images(*(paths[name] for name in ('healthy', 'before', 'after', 'mask')))
            self.assertGreater(result['numerical_improvement'], 0)
            self.assertEqual(result['mask_pixels'], 1, 'Opaque black background is protected, not editable.')
            self.assertEqual(result['outside_mask_changed_pixels'], 1)
            self.assertEqual(result['outside_pixels_status'], 'fail')
            self.assertEqual(result['semantic_identity_status'], 'unknown')
            self.assertEqual(original, {name: path.read_bytes() for name, path in paths.items()})

    def _cli(self, archive, output):
        process = subprocess.run([sys.executable, str(ROOT / 'scripts/qualify_diagnostic_evidence.py'),
            '--verify-only', '--archive', str(archive), '--output', str(output)],
            cwd=ROOT, capture_output=True, text=True, timeout=45)
        reports = list((output / 'runs').glob('*/report.json'))
        self.assertEqual(len(reports), 1, process.stdout[-4000:] + process.stderr[-4000:])
        return process, json.loads(reports[0].read_bytes()), reports[0].with_name('review.html')

    def test_rehashed_foreign_glb_packet_cannot_borrow_frozen_reference_reload_proof(self):
        # Verify the actual one-call archive before using it as an adversarial
        # source. The fixture and its observed provider output remain untouched.
        original = verify_archive(ATTEMPT)
        self.assertEqual(original['packet_sha256'], FROZEN_PACKET)
        original_glb = next(asset for asset in original['assets'] if asset['role'] == 'glb')
        with tempfile.TemporaryDirectory(prefix='qualification-glb-guard-') as temporary:
            folder = Path(temporary)
            baseline, baseline_report, _ = self._cli(ATTEMPT, folder / 'baseline')
            self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
            self.assertEqual(baseline_report['technical_status'], 'completed')
            self.assertEqual(baseline_report['technical_errors'], [])
            self.assertEqual(baseline_report['reference']['source_glb_sha256'], original_glb['sha256'])

            manifest = json.loads((ATTEMPT / 'source-manifest.json').read_bytes())
            source = folder / 'source'
            source.mkdir()
            foreign = None
            for asset in manifest['assets']:
                raw = (ATTEMPT / 'objects' / asset['sha256']).read_bytes()
                if asset['role'] == 'glb':
                    magic, version, length = struct.unpack_from('<4sII', raw)
                    self.assertEqual((magic, version, length), (b'glTF', 2, len(raw)))
                    chunk_length, chunk_type = struct.unpack_from('<I4s', raw, 12)
                    self.assertEqual(chunk_type, b'JSON')
                    document = json.loads(raw[20:20 + chunk_length])
                    document['asset'].setdefault('extras', {})['unbound_qualification_copy'] = True
                    encoded = json.dumps(document, separators=(',', ':')).encode('utf-8')
                    encoded += b' ' * ((-len(encoded)) % 4)
                    chunks = struct.pack('<I4s', len(encoded), b'JSON') + encoded + raw[20 + chunk_length:]
                    foreign = struct.pack('<4sII', b'glTF', 2, 12 + len(chunks)) + chunks
                    # This remains a complete GLB with unchanged geometry/BIN;
                    # its exact bytes have never received the pinned reload proof.
                    raw = foreign
                    asset['sha256'] = hashlib.sha256(raw).hexdigest()
                    asset['bytes'] = len(raw)
                    self.assertNotEqual(asset['sha256'], original_glb['sha256'])
                path = source / asset['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            self.assertIsNotNone(foreign)
            source_manifest = source / 'attempt.json'
            source_manifest.write_text(json.dumps(manifest), encoding='utf-8')
            altered_archive = folder / 'foreign-packet'
            altered = import_attempt(source_manifest, altered_archive)
            self.assertEqual(altered['integrity_status'], 'verified', 'The packet is valid; only its GLB authority is wrong.')
            self.assertNotEqual(altered['roles']['glb'], original['roles']['glb'])

            process, report, page = self._cli(altered_archive, folder / 'unbound-result')
            self.assertNotEqual(process.returncode, 0, 'An unbound GLB must not be offered as reload-verified reference evidence.')
            self.assertEqual(report['technical_status'], 'failed')
            self.assertTrue(report['technical_errors'])
            self.assertEqual(report['qualification_status'], 'fail')
            self.assertNotIn('data:model/gltf-binary;base64,' + base64.b64encode(foreign).decode('ascii'),
                             page.read_text(encoding='utf-8'))
            self.assertEqual(verify_archive(ATTEMPT)['packet_sha256'], FROZEN_PACKET)


if __name__ == '__main__':
    unittest.main()
