"""Treat workflow artifacts as bounded data, never as trusted executable code."""
from __future__ import annotations

import io
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from scripts.v2_preview_evidence import IMAGE_NAMES

ARCHIVE_LIMIT = 24 * 1024 * 1024
FILE_LIMIT = 4 * 1024 * 1024
ALLOWED_FILES = {*IMAGE_NAMES, "preview.json", "comment.md"}


def validate_run(run, *, repository, sha, run_id, attempt, workflow_id):
    """Pin the event to the actual producer, not artifact-provided provenance."""
    if (str(run.get("id")) != str(run_id) or str(run.get("run_attempt")) != str(attempt)
            or str(run.get("workflow_id")) != str(workflow_id) or run.get("head_sha") != sha
            or run.get("repository", {}).get("full_name") != repository
            or run.get("head_repository", {}).get("full_name") != repository
            or run.get("path") != ".github/workflows/v2_glb.yml"
            or run.get("status") != "completed" or run.get("event") not in ("pull_request", "push")):
        raise ValueError("Publication is not from the expected completed same-repository V2 run.")
    pulls = run.get("pull_requests", [])
    if run["event"] == "pull_request":
        if len(pulls) != 1 or type(pulls[0].get("number")) is not int or pulls[0]["number"] <= 0:
            raise ValueError("V2 producer run has no unambiguous associated PR.")
        return pulls[0]["number"]
    if run.get("head_branch") != "main" or pulls:
        raise ValueError("Only main push runs can publish a non-PR V2 preview.")
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_archive(client, artifact_id):
    """GitHub authorizes the signed URL; credentials never follow the redirect."""
    request = urllib.request.Request(f"{client.root}/actions/artifacts/{artifact_id}/zip",
        headers={"Authorization": f"Bearer {client.token}", "Accept": "application/vnd.github+json"})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise
        destination = error.headers.get("Location", "")
        parsed = urllib.parse.urlsplit(destination)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443) or not parsed.hostname
                or not any(parsed.hostname.endswith(suffix) for suffix in (
                    ".blob.core.windows.net", ".githubusercontent.com", ".actions.githubusercontent.com"))):
            raise ValueError("GitHub returned an unsupported artifact storage URL.")
        # Do not copy the Authorization header to artifact storage.
        response = urllib.request.urlopen(destination, timeout=30)
    with response:
        data = response.read(ARCHIVE_LIMIT + 1)
    if len(data) > ARCHIVE_LIMIT:
        raise ValueError("Preview artifact exceeds its archive budget.")
    return data


def extract_preview_archive(data, directory: Path):
    """No extractall: reject paths, links, executables, duplicates and zip bombs."""
    if len(data) > ARCHIVE_LIMIT:
        raise ValueError("Oversized preview archive.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if (len(names) != len(set(names)) or not set(names) <= ALLOWED_FILES
                or not {*IMAGE_NAMES, "preview.json"} <= set(names)):
            raise ValueError("Preview archive contains missing, duplicate or unexpected paths.")
        for item in entries:
            mode = item.external_attr >> 16
            if (item.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or mode & 0o111 or item.flag_bits & 1 or item.file_size > FILE_LIMIT
                    or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise ValueError("Preview archive contains an unsafe or oversized entry.")
        # Validate the entire archive before writing any individual file.
        files = {}
        for item in entries:
            with archive.open(item) as source:
                value = source.read(FILE_LIMIT + 1)
            if len(value) > FILE_LIMIT:
                raise ValueError("Preview entry exceeded its decompression budget.")
            files[item.filename] = value
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (directory / name).write_bytes(value)


def obtain_preview(client, *, run_id, attempt, directory):
    artifacts, page = [], 1
    while True:
        data = client.request(f"actions/runs/{run_id}/artifacts?per_page=100&page={page}")
        artifacts.extend(item for item in data["artifacts"] if item.get("name") == f"glb-v2-preview-{attempt}")
        if len(data["artifacts"]) < 100:
            break
        page += 1
        if page > 10:
            raise ValueError("Too many V2 artifacts.")
    if len(artifacts) != 1 or artifacts[0].get("expired") or not 0 < artifacts[0]["size_in_bytes"] <= ARCHIVE_LIMIT:
        raise ValueError("Run-specific preview artifact is missing, ambiguous, expired or oversized.")
    extract_preview_archive(download_archive(client, artifacts[0]["id"]), directory)
