"""Verify frozen inputs without importing the state machine or host runtime."""
import json
from pathlib import Path

from scripts.appearance_diagnostic_corpus.authoring import sha256
from . import CORPUS_VERSION,FROZEN_MANIFEST_SHA256,SCHEMA_VERSION


def checked(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Loop corpus path escapes root")
    return path


def load_manifest(root):
    data=(root/"manifest.json").read_bytes()
    if sha256(data)!=FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen loop manifest changed; review a new corpus version")
    manifest=json.loads(data)
    if manifest["corpus_version"]!=CORPUS_VERSION or manifest["schema_version"]!=SCHEMA_VERSION:
        raise ValueError("Unsupported loop corpus")
    repo=Path(__file__).resolve().parents[2]
    for record in manifest["assets"]:
        if sha256(checked(root,record["path"]).read_bytes())!=record["sha256"]:
            raise ValueError("Original loop asset changed: "+record["path"])
    for record in manifest["parents"].values():
        if sha256(checked(repo,record["path"]).read_bytes())!=record["sha256"]:
            raise ValueError("Frozen upstream corpus changed: "+record["path"])
    for record in manifest["provenance"]["generator_sources"]:
        if sha256(checked(repo,record["path"]).read_bytes().replace(b"\r\n",b"\n"))!=record["sha256_lf"]:
            raise ValueError("Original loop recipe changed: "+record["path"])
    return manifest,sha256(data)
