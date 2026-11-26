"""Installed library, actual GLB regeneration and packaged extension acceptance."""

import argparse, hashlib, json, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            [str(v) for v in command],
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=240,
        )
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    args.blender = args.blender.resolve()
    args.extension = args.extension.resolve()
    # This script is run with -I in a Python environment containing the wheel.
    import meshvenn_humanoid

    assert "bpy" not in sys.modules
    installed = Path(meshvenn_humanoid.__file__).resolve()
    if installed.is_relative_to(ROOT / "packages"):
        raise AssertionError("Use the installed library, not checkout imports")
    fixture = ROOT / "example/v2/generated/StytchDummy8Views"
    provenance = json.loads((fixture / "provenance.json").read_text())
    for path, digest in provenance["files"].items():
        assert sha(fixture / path) == digest, path
    source = fixture / "rig-baseline.glb"
    source_sha = sha(source)

    def inspect(input_path, output):
        run(
            [
                sys.executable,
                "-I",
                "-m",
                "meshvenn_humanoid",
                "--blender",
                args.blender,
                "--engine-root",
                ROOT,
                "--source",
                input_path,
                "--output",
                output,
            ],
            output.with_suffix(".log"),
        )
        return json.loads((output / "session.json").read_text())

    bad = inspect(source, args.output / "regeneration")
    assert bad["status"] == "checks_passed" and bad["selected"]["id"] != "baseline"
    assert bad["baseline"]["checks"]["proximal_link_error"] == "fail"
    assert bad["baseline"]["checks"]["distal_link_error"] == "fail"
    narrow = [r for r in bad["attempts"] if r["recipe"].startswith("local-")]
    assert len(narrow) == 2 and all(
        r["assessment"]["checks"]["elbow_inverted_area_fraction"] == "fail"
        for r in narrow
    )
    assert bad["best"]["measurements"]["elbow_inverted_area_fraction"] == 0
    assert all(v == "pass" for v in bad["best"]["checks"].values())
    selected = args.output / "regeneration/selected.glb"
    assert sha(selected) == bad["selected"]["sha256"]
    healthy = inspect(selected, args.output / "already-healthy")
    assert healthy["selected"]["id"] == "baseline" and not healthy["attempts"]
    assert sha(args.output / "already-healthy/selected.glb") == sha(selected)
    avocado = ROOT / "example/v2/assets/Avocado.glb"
    avocado_sha = sha(avocado)
    nonhuman = inspect(avocado, args.output / "nonhumanoid")
    assert nonhuman["status"] == "not_applicable" and nonhuman["selected"] is None
    assert not (args.output / "nonhumanoid/selected.glb").exists()
    assert sha(source) == source_sha and sha(avocado) == avocado_sha
    extension = args.output / "isolated/meshvenn_humanoid_auto"
    with zipfile.ZipFile(args.extension) as archive:
        archive.extractall(extension)
    wheel = next((extension / "wheels").glob("*.whl"))
    site = args.output / "isolated/site-packages"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site)
    run(
        [
            args.blender,
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            ROOT / "tests/blender_humanoid_pipeline.py",
            "--",
            "--source",
            source,
            "--output",
            args.output / "pipeline",
            "--extension-root",
            extension,
            "--site-packages",
            site,
        ],
        args.output / "pipeline.log",
    )
    report = dict(
        installed_package=str(installed),
        source_sha256=source_sha,
        selected_sha256=sha(selected),
        rejected_narrow_recipes=len(narrow),
        selected_recipe=next(
            r["recipe"] for r in bad["attempts"] if r["asset"] == bad["selected"]
        ),
        healthy_retained_exact=True,
        nonhumanoid_unchanged=True,
        packaged_extension_pipeline=True,
        quality_certification="unknown",
        consumer_acceptance="unknown",
    )
    (args.output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
