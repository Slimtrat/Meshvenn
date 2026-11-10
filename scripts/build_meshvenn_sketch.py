"""Build the independent, engine-free Meshvenn Sketch Blender extension."""
import argparse
import os
from pathlib import Path
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'extensions' / 'meshvenn_sketch'


def build(destination=None):
    manifest = tomllib.loads((SOURCE / 'blender_manifest.toml').read_text(encoding='utf-8'))
    destination = Path(destination or ROOT / 'dist' / f"{manifest['id']}-{manifest['version']}.zip")
    if destination.suffix.lower() != '.zip':
        raise ValueError('Choose a .zip output file.')
    if destination.exists():
        raise FileExistsError(f'Refusing to replace {destination}')
    # An allowlist keeps engine modules, native libraries, test fixtures and caches out.
    # Git checkouts may use LF or CRLF. Package the same UTF-8 text on every OS.
    def content(path):return path.read_text(encoding='utf-8').encode('utf-8')
    files = {path.name: content(path) for path in SOURCE.glob('*.py')}
    for name in ('blender_manifest.toml', 'README.md'):
        files[name] = content(SOURCE / name)
    files['LICENSE'] = content(ROOT / 'LICENSE')
    if '__init__.py' not in files or manifest['id'] != 'meshvenn_sketch':
        raise ValueError('Not the standalone Meshvenn Sketch extension.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.zip', delete=False) as stream:
            staged = Path(stream.name)
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        os.link(staged, destination)  # Atomic publication without replacing another file.
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    print(build(parser.parse_args().output).resolve())
