"""Blender entrypoint: --background --python this-file -- --output fresh-directory."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from chamber_props.author import main

if __name__=='__main__':main()
