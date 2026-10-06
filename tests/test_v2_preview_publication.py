"""Trusted publication operates on bounded data and cannot replace a newer head/run."""
from __future__ import annotations

import io
import stat
import tempfile
import urllib.error
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from scripts.publish_v2_preview import current_pr, newest_producer, publish_images, update_comment
from scripts.v2_preview_evidence import IMAGE_NAMES, MARKER
from scripts.v2_preview_run import FILE_LIMIT, download_archive, extract_preview_archive, validate_run

SHA = "1" * 40
REPO = "Slimtrat/Meshvenn"
ROOT = Path(__file__).resolve().parents[1]


def archive(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name in (*IMAGE_NAMES, "preview.json"):
            zipped.writestr(name, b"data")
        if extra:
            zipped.writestr(*extra)
    return buffer.getvalue()


class Client:
    def __init__(self, comments=None, pull=None):
        self.calls, self.comments, self.pull = [], comments or [], pull or {
            "state": "open", "head": {"sha": SHA, "repo": {"full_name": REPO}}}

    def request(self, path, *, method="GET", data=None):
        self.calls.append((path, method, data))
        if path.startswith("pulls/"):
            return self.pull
        if path.startswith("issues/1/comments?"):
            return self.comments
        if path == "git/ref/heads/visual-preview-assets":
            return {"object": {"sha": "parent"}}
        if path == "git/commits/parent":
            return {"tree": {"sha": "parent-tree"}}
        return {"sha": "new-commit"}


class PreviewPublicationTests(unittest.TestCase):
    def test_signed_artifact_download_never_forwards_the_github_token(self):
        class Token:
            root, token = "https://api.github.com/repos/Slimtrat/Meshvenn", "private-token"
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                self.limit = limit
                return b"zip"
        destination = "https://tenant.blob.core.windows.net/asset.zip?sig=signed"
        redirect = urllib.error.HTTPError("github", 302, "redirect", {"Location": destination}, None)
        with patch("scripts.v2_preview_run.urllib.request.build_opener") as opener, patch(
                "scripts.v2_preview_run.urllib.request.urlopen", return_value=Response()) as download:
            opener.return_value.open.side_effect = redirect
            self.assertEqual(download_archive(Token(), 1), b"zip")
            initial = opener.return_value.open.call_args.args[0]
            self.assertEqual(initial.get_header("Authorization"), "Bearer private-token")
            self.assertEqual(download.call_args.args, (destination,))
            self.assertEqual(download.call_args.kwargs, {"timeout": 30})
        for unsafe in ("http://tenant.blob.core.windows.net/a", "https://evil.test/a", "file:///etc/passwd"):
            with patch("scripts.v2_preview_run.urllib.request.build_opener") as opener:
                opener.return_value.open.side_effect = urllib.error.HTTPError("github", 302, "redirect", {"Location": unsafe}, None)
                with self.assertRaises(ValueError):
                    download_archive(Token(), 1)

    def test_workflows_keep_privileges_out_of_the_pr_producer(self):
        producer = (ROOT / ".github/workflows/v2_glb.yml").read_text("utf-8")
        publisher = (ROOT / ".github/workflows/v2_preview_publish.yml").read_text("utf-8")
        legacy = (ROOT / ".github/workflows/visual_preview.yml").read_text("utf-8")
        self.assertIn("contents: read", producer)
        self.assertNotIn("contents: write", producer)
        self.assertNotIn("pull-requests: write", producer)
        self.assertNotIn("--publish", producer)
        self.assertIn("glb-v2-preview-${{ github.run_attempt }}", producer)
        self.assertIn("workflow_run:", publisher)
        self.assertNotIn("pull_request_target", publisher)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", publisher)
        self.assertNotIn("ref: ${{ github.event.workflow_run.head_sha }}", publisher)
        self.assertIn("persist-credentials: false", publisher)
        self.assertNotIn("download-artifact", publisher)
        self.assertIn("--publish", publisher)
        self.assertNotIn("<!-- bpt-visual-preview -->", legacy)
        self.assertIn("<!-- bpt-legacy-visual-preview -->", legacy)

    def test_a_newer_failed_or_running_producer_makes_older_results_stale(self):
        class Runs:
            def request(self, path):
                return {"workflow_runs": self.runs}
        client = Runs()
        original = {"id": 10, "run_attempt": 1, "head_sha": SHA, "head_branch": "codex/branch", "event": "pull_request"}
        client.runs = [original]
        self.assertTrue(newest_producer(client, original))
        client.runs.append({**original, "id": 11, "conclusion": "failure"})
        self.assertFalse(newest_producer(client, original))
        client.runs = [{**original, "run_attempt": 2, "status": "in_progress"}]
        self.assertFalse(newest_producer(client, original))

    def test_only_open_same_repository_current_head_is_writable(self):
        self.assertTrue(current_pr(Client(), 1, SHA, REPO))
        for pull in ({"state": "closed", "head": {"sha": SHA, "repo": {"full_name": REPO}}},
                     {"state": "open", "head": {"sha": "2" * 40, "repo": {"full_name": REPO}}},
                     {"state": "open", "head": {"sha": SHA, "repo": {"full_name": "fork/Meshvenn"}}}):
            self.assertFalse(current_pr(Client(pull=pull), 1, SHA, REPO))

    def test_no_user_marker_hijack_and_no_older_run_overwrite(self):
        client = Client(comments=[{"id": 2, "body": MARKER, "user": {"login": "human"}}])
        update_comment(client, 1, MARKER + " safe")
        self.assertEqual(client.calls[-1][1], "POST")
        body = MARKER + f"\n<!-- meshvenn-v2-run:11:2:{SHA} -->"
        client = Client(comments=[{"id": 2, "body": body, "user": {"login": "github-actions[bot]"}}])
        update_comment(client, 1, MARKER + f"\n<!-- meshvenn-v2-run:10:1:{SHA} -->")
        self.assertEqual(len(client.calls), 1)
        update_comment(client, 1, MARKER + f"\n<!-- meshvenn-v2-run:11:3:{SHA} -->")
        self.assertEqual(client.calls[-1][0], "issues/comments/2")

    def test_asset_namespace_preserves_legacy_tree_and_never_force_pushes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in IMAGE_NAMES:
                (root / name).write_bytes(b"png")
            client = Client()
            publish_images(client, root, f"v2/pr/1/{SHA}/10-1")
        trees = [data for path, _, data in client.calls if path == "git/trees"]
        self.assertEqual(trees[0]["base_tree"], "parent-tree")
        self.assertTrue(all(entry["path"].startswith("v2/pr/1/") for entry in trees[0]["tree"]))
        self.assertEqual(client.calls[-1][2]["force"], False)

    def test_producer_identity_cannot_be_supplied_by_artifact(self):
        run = {"id": 10, "run_attempt": 1, "workflow_id": 3, "head_sha": SHA,
               "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
               "path": ".github/workflows/v2_glb.yml", "status": "completed", "event": "pull_request",
               "pull_requests": [{"number": 1}]}
        args = dict(repository=REPO, sha=SHA, run_id="10", attempt="1", workflow_id=3)
        self.assertEqual(validate_run(run, **args), 1)
        for key, value in (("run_attempt", 2), ("workflow_id", 4), ("head_sha", "2" * 40),
                           ("path", ".github/workflows/other.yml"), ("pull_requests", []),
                           ("event", "workflow_dispatch"), ("status", "in_progress")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_run({**run, key: value}, **args)

    def test_zip_data_only_no_paths_duplicates_links_executables_or_big_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "bundle"
            extract_preview_archive(archive(), directory)
            self.assertEqual((directory / "preview.json").read_bytes(), b"data")
            symlink = zipfile.ZipInfo("comment.md")
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            executable = zipfile.ZipInfo("comment.md")
            executable.external_attr = (stat.S_IFREG | 0o755) << 16
            for entry in (("../stolen.txt", b"data"), ("run.py", b"print('bad')"),
                          ("pose.png", b"duplicate"), (symlink, b"/tmp/elsewhere"),
                          (executable, b"executable"), ("comment.md", b"x" * (FILE_LIMIT + 1))):
                with self.subTest(entry=str(entry[0])), self.assertRaises(ValueError):
                    extract_preview_archive(archive(entry), directory)


if __name__ == "__main__":
    unittest.main()
