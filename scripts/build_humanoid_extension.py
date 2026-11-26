"""Package the optional supervisor with its independent, prebuilt Python wheel."""

import argparse, os, tempfile, tomllib, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(wheel, output=None):
    source = ROOT / "extensions/meshvenn_humanoid_auto"
    manifest = tomllib.loads(
        (source / "blender_manifest.toml").read_text(encoding="utf-8")
    )
    wheel = Path(wheel).resolve(strict=True)
    if wheel.name != Path(manifest["wheels"][0]).name:
        raise ValueError("Wheel version does not match extension manifest")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if (
            "meshvenn_humanoid/loop.py" not in names
            or "meshvenn_humanoid/blender/worker.py" not in names
        ):
            raise ValueError("Incomplete humanoid wheel")
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
    files["wheels/" + wheel.name] = wheel.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".zip", delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(build(args.wheel, args.output))
