"""Re-export the extracted delivery with its original reference checkout unavailable."""
import argparse
import importlib.util
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--delivery',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
path=args.delivery/'Source/author.py'
spec=importlib.util.spec_from_file_location('portable_workshop_author',path)
author=importlib.util.module_from_spec(spec);spec.loader.exec_module(author)
author.ROOT=None;author.TARGET=None
author.run(args.output.resolve(),(args.delivery/'source.blend').resolve())
assert not any(n.startswith(('meshvenn_sketch','blender_projection_tool')) for n in sys.modules)
print('WORKSHOP PORTABLE PASS: extracted source re-exported with no reference checkout or engine/add-on imports.')
