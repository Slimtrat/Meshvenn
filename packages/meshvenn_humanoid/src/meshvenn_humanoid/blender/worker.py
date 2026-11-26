"""Isolated Blender host, executable from an installed wheel or a checkout."""

import argparse, importlib.util, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from meshvenn_humanoid import Asset, Budget, HumanoidLoop
from meshvenn_humanoid.blender.port import BlenderHumanoidPort


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine-root", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--object")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--max-attempts", type=int, default=4)
    p.add_argument("--max-seconds", type=float, default=180.0)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    root = a.engine_root.resolve(strict=True)
    name = "meshvenn_humanoid_host_engine"
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    engine = importlib.util.module_from_spec(spec)
    sys.modules[name] = engine
    spec.loader.exec_module(engine)
    engine.register()
    output = a.output.resolve()
    source = a.source.resolve(strict=True)
    cancel = output / "cancel.request"
    port = BlenderHumanoidPort(name, source, output, object_name=a.object)
    state = HumanoidLoop(
        port, output, budget=Budget(a.max_attempts, a.max_seconds)
    ).run(resume=a.resume, cancel=cancel.exists)
    if state["selected"] is not None:
        asset = Asset(**state["selected"])
        port.verify(asset)
        original = output / asset.id / "character.glb"
        target = output / "selected.glb"
        if target.exists():
            if target.read_bytes() != original.read_bytes():
                raise ValueError("Previous selection changed")
        else:
            shutil.copyfile(original, target)
    print(
        json.dumps(
            {
                k: state[k]
                for k in (
                    "status",
                    "selected",
                    "elapsed_seconds",
                    "quality_certification",
                )
            },
            indent=2,
        )
    )
    return 0 if state["status"] in ("checks_passed", "not_applicable") else 2


if __name__ == "__main__":
    raise SystemExit(main())
