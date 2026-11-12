"""Verify original appearance evidence without invoking a diagnostic engine."""
from __future__ import annotations

import json
from pathlib import Path

from . import CORPUS_VERSION, FROZEN_MANIFEST_SHA256, SCHEMA_VERSION
from .authoring import sha256


def checked_path(root: Path, relative: str) -> Path:
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Appearance corpus asset escapes its root")
    return path


def load_manifest(root: Path):
    data = (root/"manifest.json").read_bytes()
    document = json.loads(data)
    if document.get("schema_version") != SCHEMA_VERSION or document.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("Unsupported appearance corpus version")
    if sha256(data) != FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen appearance manifest changed; use a reviewed new corpus version")
    records = [document["review_panel"]]
    for case in document["cases"]:
        records.extend((case["source"],case["mesh"]))
        for variant in case["variants"]:
            for view in variant["views"].values():
                records.extend((view,view["truth_region_mask"]))
    for record in records:
        if sha256(checked_path(root,record["path"]).read_bytes()) != record["sha256"]:
            raise ValueError("Appearance authoring evidence changed: " + record["path"])
    for name, digest in document["generator_source_sha256_lf_normalized"].items():
        if sha256((Path(__file__).parent/name).read_bytes().replace(b"\r\n",b"\n")) != digest:
            raise ValueError("Frozen appearance authoring code changed: " + name)
    return document, sha256(data)
