"""Verify cached organic diagnostic profiles against a real rendered sheet."""
import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.sdf.projection import build_signed_distance_mask
from scripts.generate_example_native_support.pipeline import process_sheet
from scripts.run_logger import RunLogger


def main():
    argv = sys.argv[sys.argv.index('--')+1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args(argv)
    options = argparse.Namespace(
        resolution=32,threshold=.1,sheet_white_threshold=.94,profiles=['L2','L4','L10'],
        thread_count=0,symmetry_x=False,voxel_size=1.,target_height=2.,
        mesh_mode='surface_nets',skip_blend=True,surface_refinement='organic',
    )
    with patch('core.sdf.projection.build_signed_distance_mask',wraps=build_signed_distance_mask) as build:
        process_sheet(args.source,args.output,options,logger=RunLogger())
        assert build.call_count == 10, 'Distance fields were rebuilt for each diagnostic profile'
    manifest = json.loads((args.output/args.source.stem/'manifest.json').read_text('utf-8'))
    profiles = manifest['profiles']
    for name in ('L2','L4','L10'):
        finish = profiles[name]['surface_refinement']
        assert finish['algorithm'] == 'contour-taubin-v2'
        assert finish['micro_finish']['algorithm'] == 'bounded-laplacian-v1'
        assert finish['micro_finish']['iterations'] == 6
        assert finish['maximum_displacement_in_voxels'] <= .75
        assert finish['face_orientation_preserved'] and finish['topology_preserved']
    print('Organic L2/L4/L10 profiles share one ten-view contour cache: PASS')


if __name__ == '__main__':
    main()
