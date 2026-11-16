"""Safely rebuild original references into a NEW explicit output directory.

Blender usage: --python scripts/build_diagnostic_reference.py -- --output NEW_DIR
Read-only verification: add --verify-glb-only and select an existing fixture.
Historical authoring bytes are archived separately; the frozen corpus is never
the default destination of this public command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/"tests/fixtures/diagnostics/provider-authoring-v1/build_diagnostic_reference.py"
AUTHOR_SHA256="6eab89f7cab7d5fc059051e0ecd833dcaea220d89901536ea8c19e6620257ce9"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verify-glb-only",action="store_true")
    arguments=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    args=parser.parse_args(arguments)
    output=args.output.resolve()
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=AUTHOR_SHA256:
        parser.error("The archived historical authoring source changed.")
    if args.verify_glb_only:
        if not output.is_dir() or not (output/"original-reference.glb").is_file():
            parser.error("Read-only verification requires an existing reference directory and GLB.")
    else:
        try:output.mkdir(parents=True,exist_ok=False)
        except OSError as exc:parser.error("Build requires a NEW output directory; existing paths are never reused: "+str(exc))
    # The archived file retains its exact historical __file__-relative code.
    # Supply the repository import root and an explicit absolute destination.
    sys.path.insert(0,str(ROOT))
    original_argv=sys.argv[:]
    try:
        sys.argv=[sys.argv[0],"--","--output",str(output)]+(["--verify-glb-only"] if args.verify_glb_only else [])
        runpy.run_path(str(ARCHIVE),run_name="__main__")
    finally:sys.argv=original_argv
    if not args.verify_glb_only:
        proof=dict(schema_version=1,active_wrapper_path="scripts/build_diagnostic_reference.py",
            active_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            archived_authoring_path=ARCHIVE.relative_to(ROOT).as_posix(),archived_authoring_sha256=AUTHOR_SHA256,
            fresh_manifest_sha256=hashlib.sha256((output/"manifestfixture.json").read_bytes()).hexdigest())
        (output/"fresh-build-wrapper.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="\n")


if __name__=="__main__":main()
