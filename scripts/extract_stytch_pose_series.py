"""Project authorized matrices/provenance; never publish private consumer captures."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_capture import project_capture

REVISION = "1c9040e51be1e757c974eca794604cb9553cb532"
SOURCE_BASE = "godot/Stytch.GodotHost/Assets/Embodiment/Candidates/MeshVennDollModularV1/Evidence/Factory/"
ASSET_SHA = "76590fd9c335335255f2eb2a4fc0866adf3c5a6a6fad0d4938c9e7550b7dcb57"
SOURCE_BLOBS = {
    "factory-hall.pose.json": "a64317a3c6cf54448b3fbe47306c8eb4f7384f91",
    "factory-held.pose.json": "ce8e90b307fb2c1cc67e3db89b770deeeab923ad",
    "factory-one-leg.pose.json": "503adc294db5a95483697a2372c8e44526b8f092",
    "Walk/meshvenn-walk-00.pose.json": "fa514e453da08f1b2010b134cf90d6eccfce4a8a",
    "Walk/meshvenn-walk-01.pose.json": "0ca9bd6a2ca2a54294e1dc0d7fe44509a03fd732",
    "Walk/meshvenn-walk-02.pose.json": "787ab211de264ab4a47b95c037ec248592638b0e",
    "World/03-one-leg-hop.pose.json": "d9987541502d5d01a2a454ae6098d57519474aa5",
    **{f"Hop/meshvenn-hop-{i:02}.pose.json": blob for i, blob in enumerate((
        "53c3974c9bed70f06096749cf27af90402246dbf", "37963093c8567564c3f8cab55e56279e1ac844cf",
        "881a2330105c55430de8b38b537f70f053d02167", "836ce2a10a1b1f52112c81aa1db7431e4bbc7547",
        "ce6553f8e9b84a9e983aead25d698a46ce9dd4d8", "8f9ef92af66f076d341b502a1726faa26634c965",
        "f7136df1b0998c185975f8736475460a1651d17b", "d852b63f8f10f735cdc93b1c7d95845de4315799",
        "a0c79dedfcba7bc893c7746c10aa5873cc23f479", "e35b38a63b8e852d089b9697543bf0728252cb25",
        "420a99a444e72b839f82c54c586eab76b26aa772", "3949012bcd4bbf9e242358cb9f4a5cdcfd348b1b"))},
}
INDEX_SHA256 = "5023701a1036067891bb961e527dc69d35e57973339ebad1c5e58d469d8e79c7"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n").encode("utf-8")


def verify_source_blob(name, raw):
    blob = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    if SOURCE_BLOBS.get(name) != blob:
        raise ValueError("Input JSON bytes differ from the pinned Stytch revision.")
    return blob


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input.resolve(strict=True), args.output.resolve()
    files = {p.relative_to(source).as_posix(): p for p in source.rglob("*.pose.json")}
    if set(files) != set(SOURCE_BLOBS) or output == source or (output.exists() and any(output.iterdir())):
        raise ValueError("Require all nineteen captured pairs and a separate empty output directory.")
    prepared, entries = [], []
    for name, path in sorted(files.items()):
        raw = path.read_bytes()
        blob = verify_source_blob(name, raw)
        document, proof, metadata = project_capture(strict_json_loads(raw.decode("utf-8")))
        if document["AssetSha256"].lower() != ASSET_SHA:
            raise ValueError("Capture targets a different native GLB fingerprint.")
        png = path.with_name(metadata["capture_filename"])
        if digest(png.read_bytes()) != metadata["capture_sha256"]:
            raise ValueError(f"Capture PNG hash mismatch for {name}.")
        case_id = name.removesuffix(".pose.json").replace("/", "-")
        probe_file, proof_file = case_id+".json", case_id+".matrices.json"
        probe_bytes, proof_bytes = encoded(document), encoded(proof)
        prepared.extend(((probe_file, probe_bytes), (proof_file, proof_bytes)))
        entries.append({"id": case_id, "probe": probe_file, "probe_sha256": digest(probe_bytes),
                        "matrix_proof": proof_file, "matrix_proof_sha256": digest(proof_bytes),
                        "source_path": SOURCE_BASE+name, "source_json_sha256": digest(raw),
                        "source_git_blob": blob,
                        "movement_classification": "walk-approach, not explicit hop" if name.startswith("World/") else metadata["context"].get("Pose"),
                        **metadata})
    index = {"schema_version": 1, "source_repository": "Stytch0/Stytch", "source_revision": REVISION,
             "asset_sha256": ASSET_SHA, "case_count": len(entries), "cases": entries,
             "publication": "Owner explicitly authorized publication of matrices and provenance. Private PNGs, control/loadout data, node names and world telemetry are excluded.",
             "scope": "Exact nineteen synchronized source poses and visibility; no consumer repair or full visual/physical-contact qualification."}
    # All validation precedes publication; bytes are mechanically projected,
    # never replaced with invented pose targets or unchecked private fields.
    if digest(encoded(index)) != INDEX_SHA256:
        raise ValueError("Projected dataset changed; update its explicit qualification pin first.")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in prepared:
        (output / name).write_bytes(data)
    (output / "index.json").write_bytes(encoded(index))
    print("Projected nineteen validated matrix pairs; no private PNG, code or telemetry published.")


if __name__ == "__main__":
    main()
