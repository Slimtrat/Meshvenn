"""Publish SHA/run-addressed images and one stale-safe V2 sticky comment.

Publication executes only trusted default-branch code in workflow_run; producer
artifacts are validated data, never executable code. PR jobs remain read-only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v2_preview_evidence import MARKER, IMAGE_NAMES, build_comment, verified_evidence
from scripts.v2_preview_run import obtain_preview, validate_run

ASSET_BRANCH = "visual-preview-assets"


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid preview repository.")
        self.root = f"https://api.github.com/repos/{repository}"
        self.token = token

    def request(self, path, *, method="GET", data=None):
        request = urllib.request.Request(self.root + "/" + path, method=method,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


def current_pr(client, number, sha, repository):
    pull = client.request(f"pulls/{number}")
    return (pull["state"] == "open" and pull["head"]["sha"] == sha
            and pull["head"]["repo"]["full_name"] == repository)


def newest_producer(client, run):
    """An older completion cannot replace a newer failed/in-progress attempt."""
    branch = urllib.parse.quote(run["head_branch"], safe="")
    candidates = client.request(
        f"actions/workflows/v2_glb.yml/runs?branch={branch}&event={run['event']}&per_page=100")["workflow_runs"]
    matching = [item for item in candidates if item.get("head_sha") == run["head_sha"]]
    return (bool(matching) and max((int(item["id"]), int(item["run_attempt"])) for item in matching)
            == (int(run["id"]), int(run["run_attempt"])))


def publish_images(client, directory, prefix):
    """Append immutable PNGs in an isolated namespace; preserve other workflow assets."""
    entries = []
    for name in IMAGE_NAMES:
        blob = client.request("git/blobs", method="POST", data={
            "encoding": "base64", "content": base64.b64encode((directory / name).read_bytes()).decode("ascii")})
        entries.append({"path": f"{prefix}/{name}", "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for _ in range(4):
        try:
            ref = client.request(f"git/ref/heads/{ASSET_BRANCH}")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            ref = None
        parents = [ref["object"]["sha"]] if ref else []
        tree_input = {"tree": entries}
        if parents:
            parent = client.request(f"git/commits/{parents[0]}")
            tree_input["base_tree"] = parent["tree"]["sha"]
        tree = client.request("git/trees", method="POST", data=tree_input)
        commit = client.request("git/commits", method="POST", data={
            "message": f"preview: V2 evidence {prefix}", "tree": tree["sha"], "parents": parents})
        try:
            if parents:
                client.request(f"git/refs/heads/{ASSET_BRANCH}", method="PATCH",
                               data={"sha": commit["sha"], "force": False})
            else:
                client.request("git/refs", method="POST", data={"ref": f"refs/heads/{ASSET_BRANCH}", "sha": commit["sha"]})
            return commit["sha"]
        except urllib.error.HTTPError as error:
            if error.code not in (409, 422):
                raise
    raise RuntimeError("Preview asset branch kept advancing; no existing asset was overwritten.")


def update_comment(client, number, body):
    comments, page = [], 1
    while True:
        batch = client.request(f"issues/{number}/comments?per_page=100&page={page}")
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    # Only the bot's marker is owned by this workflow. A user can mention it safely.
    existing = next((item for item in reversed(comments) if MARKER in (item.get("body") or "")
                     and item.get("user", {}).get("login") == "github-actions[bot]"), None)
    revision = r"<!-- meshvenn-v2-run:(\d+):(\d+):([a-f0-9]{40}) -->"
    incoming = re.search(revision, body)
    previous = re.search(revision, existing["body"]) if existing else None
    if incoming and previous and incoming[3] == previous[3]:
        if tuple(map(int, previous.group(1, 2))) > tuple(map(int, incoming.group(1, 2))):
            print("Comment skipped: a newer run/attempt already owns this revision's comment.")
            return
    path = f"issues/comments/{existing['id']}" if existing else f"issues/{number}/comments"
    client.request(path, method="PATCH" if existing else "POST", data={"body": body})


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", default="1")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--artifact-url", default="")
    parser.add_argument("--image-root", default="")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not args.run_id.isdigit() or not args.run_attempt.isdigit():
        raise ValueError("Invalid workflow run identity.")
    run_url = f"https://github.com/{args.repository}/actions/runs/{args.run_id}"
    report, reason, image_root, client = None, None, None, None
    artifact_obtained = False
    if args.publish:
        client = GitHub(args.repository, os.environ["GH_TOKEN"])
        producer = client.request(f"actions/runs/{args.run_id}")
        workflow = client.request("actions/workflows/v2_glb.yml")
        args.pr_number = validate_run(producer, repository=args.repository, sha=args.source_sha,
            run_id=args.run_id, attempt=args.run_attempt, workflow_id=workflow["id"])
        args.status = producer["conclusion"]
        if not newest_producer(client, producer):
            print("Preview skipped: a newer V2 run/attempt owns this revision.")
            return
        if args.pr_number and not current_pr(client, args.pr_number, args.source_sha, args.repository):
            print("Preview skipped: PR closed, forked, or advanced to another head.")
            return
        if args.status == "success":
            try:
                obtain_preview(client, run_id=args.run_id, attempt=args.run_attempt, directory=args.evidence)
                artifact_obtained = True
            except (ValueError, OSError, zipfile.BadZipFile, urllib.error.HTTPError, urllib.error.URLError) as error:
                reason = f"Artefact de cette tentative indisponible ({type(error).__name__})."
    if args.status == "success" and (client is None or artifact_obtained):
        try:
            report = verified_evidence(args.evidence, args.source_sha, args.run_id, args.run_attempt)
        except (ValueError, AssertionError, KeyError, TypeError, RecursionError, OSError) as error:
            # Never interpolate attacker-controlled JSON field names into Markdown.
            reason = f"Bundle V2 absent ou invalide ({type(error).__name__})."
    if client:
        if report is not None:
            scope = f"pr/{args.pr_number}" if args.pr_number else "main"
            prefix = f"v2/{scope}/{args.source_sha}/{args.run_id}-{args.run_attempt}"
            try:
                asset_commit = publish_images(client, args.evidence, prefix)
                image_root = f"https://raw.githubusercontent.com/{args.repository}/{asset_commit}/{prefix}"
            except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as error:
                # Presentation may fail, but never masquerades as a successful render.
                reason = f"Publication des PNG indisponible ({type(error).__name__})."
    else:
        image_root = args.image_root or None
    body = build_comment(sha=args.source_sha, run_url=run_url, status=args.status, evidence=report,
                         image_root=image_root, artifact_url=args.artifact_url or None, reason=reason)
    body += f"\n<!-- meshvenn-v2-run:{args.run_id}:{args.run_attempt}:{args.source_sha} -->\n"
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "comment.md").write_text(body, "utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as destination:
            destination.write(body + "\n")
    if client and args.pr_number:
        # Re-check after publication, before touching an existing current-head comment.
        validate_run(client.request(f"actions/runs/{args.run_id}"), repository=args.repository,
                     sha=args.source_sha, run_id=args.run_id, attempt=args.run_attempt, workflow_id=workflow["id"])
        if not newest_producer(client, producer):
            print("Comment skipped: a newer V2 run began while assets were publishing.")
            return
        if not current_pr(client, args.pr_number, args.source_sha, args.repository):
            print("Comment skipped: PR advanced while images were publishing.")
            return
        update_comment(client, args.pr_number, body)
    print(body)


if __name__ == "__main__":
    main()
