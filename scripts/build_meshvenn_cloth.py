"""Build the independent cloth extension with no engine or example assets."""

import argparse, os, tempfile, tomllib, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output=None):
    source = ROOT / "extensions/meshvenn_cloth"
    manifest = tomllib.loads(
        (source / "blender_manifest.toml").read_text(encoding="utf-8")
    )
    destination = Path(
        output or ROOT / "dist" / f"{manifest['id']}-{manifest['version']}.zip"
    ).resolve()
    if destination.suffix != ".zip" or destination.exists():
        raise ValueError("Choose a new ZIP destination")
    files = {
        p.name: p.read_text(encoding="utf-8").encode() for p in source.glob("*.py")
    }
    for name in ("README.md", "blender_manifest.toml"):
        files[name] = (source / name).read_text(encoding="utf-8").encode()
    files["LICENSE"] = (ROOT / "LICENSE").read_text(encoding="utf-8").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".zip", delete=False
    ) as stream:
        staged = Path(stream.name)
    try:
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                archive.writestr(item, data)
        os.link(staged, destination)
    finally:
        staged.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    print(build(parser.parse_args().output))
