"""Real isolated native diagnostics from the installed/extracted Blender add-on."""
from __future__ import annotations

import argparse
import hashlib
import importlib
from pathlib import Path
import sys

import bpy


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, default=root)
    parser.add_argument('--native-library', type=Path, required=True)
    parser.add_argument('--python-executable', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    package_root = args.package_root.resolve()
    sys.path.insert(0, str(package_root.parent))
    package = importlib.import_module(package_root.name)
    assert Path(package.__file__).resolve().parent == package_root
    prefix = package.__name__
    contracts = importlib.import_module(prefix + '.core.diagnostic_contracts')
    preflight = importlib.import_module(prefix + '.core.diagnostics_preflight')
    geometry = importlib.import_module(prefix + '.core.geometry_diagnostics')
    pipeline = importlib.import_module(prefix + '.core.pipeline_contracts')
    package.register()
    try:
        before_objects = tuple(bpy.context.scene.objects)
        # At native resolution16 the occupied centres4..11 have cell footprint
        # u/v in[7/30,23/30], exactly this31pixel nearest-sample silhouette.
        size = 31
        rgba = tuple(channel for y in range(size) for x in range(size)
                     for channel in ((.2, .5, .75, 1.) if 7 <= x <= 23 and 7 <= y <= 23
                                     else (0., 0., 0., 0.)))
        raster = preflight.RasterInput.from_pixels(size, size, rgba)
        proof = contracts.ArtifactReference(
            'analytic-cube-camera', hashlib.sha256(b'native16-cube-centres4..11').hexdigest(),
            'application/x-analytic-camera-proof')
        views = tuple(contracts.ViewRevision(
            name, 1, raster.content_reference(), None,
            contracts.CameraDeclaration('orthographic', angle, 0, verified=True, verification_evidence=proof),
            origin='rendered', origin_details='Analytic native-cell fixture, not human-validated production art')
            for name, angle in (('front', 0), ('side', 90)))
        revision = contracts.ViewSetRevision('packaged-native-cube', 1, views)
        inputs = {view.view_id: preflight.ViewInput(raster) for view in views}
        originals = tuple((name, data.image.rgba, data.image.source_sha256) for name, data in inputs.items())
        backend = geometry.NativeGeometryBackend(args.native_library.resolve(),
                                                 python_executable=args.python_executable.resolve())
        policy = geometry.GeometryPolicy(resolution=16, reprojection_size=64, max_seconds=15)
        result = geometry.analyze_geometry(revision, inputs, policy=policy, backend=backend)
        assert result.volume is not None and result.volume.occupied_count > 0, result.report.to_json()
        assert result.report.verification_status == 'pass', result.report.to_json()
        assert result.provenance.completed_experiments >= 3
        assert result.provenance.library_sha256 == hashlib.sha256(args.native_library.read_bytes()).hexdigest()
        assert result.provenance.termination == 'exited'
        encoded = result.to_json()
        restored = geometry.GeometryResult.from_json(encoded)
        assert restored.to_json() == encoded
        stage = pipeline.StageExecutionResult.succeeded(
            stage=pipeline.PipelineStage.GEOMETRY, implementation_id='native-visual-hull',
            payload=restored.volume, diagnostic_report=restored.report)
        assert stage.diagnostic_report_json() == restored.report.to_json()
        assert stage.success
        cancelled = geometry.analyze_geometry(revision, inputs, policy=policy, backend=backend,
                                               cancel=lambda: True)
        assert cancelled.report.verification_status != 'pass'
        assert cancelled.report.completion == 'cancelled'
        assert restored.to_json() == encoded  # A cancelled candidate cannot mutate accepted evidence.
        assert tuple((name, data.image.rgba, data.image.source_sha256) for name, data in inputs.items()) == originals
        assert tuple(bpy.context.scene.objects) == before_objects
        print('PACKAGED_GEOMETRY_DIAGNOSTICS_PASS: actual native child, counterfactuals, report roundtrip, pipeline attachment and cancellation')
    finally:
        package.unregister()


if __name__ == '__main__':
    main()
