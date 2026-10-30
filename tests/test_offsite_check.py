"""Tests for scripts/offsite_check.py against a real temporary git repository and a fake archive API.
Run: python3 -m unittest discover -s tests -v"""
import datetime as dt
import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("offsite_check", HERE.parent / "scripts" / "offsite_check.py")
assert spec is not None and spec.loader is not None
offsite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offsite)

NOW = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.timezone.utc)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class FakeArchive:
    """Answers the three API calls the script makes; branches are served two per page to test pagination."""

    def __init__(self, branches: dict[str, str] | None, date: str = "2026-10-30T12:00:00+00:00",
                 status: str = "full"):
        self.branches, self.date, self.status = branches, date, status
        self.calls: list[tuple[str, str]] = []
        self.head = "refs/heads/main"

    def __call__(self, url: str, method: str = "GET", timeout: int = 60) -> Any:
        self.calls.append((method, url))
        if "/origin/save/" in url:
            return {"save_request_status": "accepted", "save_task_status": "pending"}
        if "/visit/latest/" in url:
            if self.branches is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
            return {"date": self.date, "snapshot": "ab" * 20, "status": self.status}
        refs = sorted((self.branches or {}).items())
        start = url.split("branches_from=")[1] if "branches_from=" in url else None
        if start:
            start = start.replace("%2F", "/")
            refs = [r for r in refs if r[0] >= start]
        page = dict(refs[:2])
        return {"branches": {r: {"target": s, "target_type": "revision"} for r, s in page.items()}
                | {"HEAD": {"target": self.head, "target_type": "alias"}},
                "next_branch": refs[2][0] if len(refs) > 2 else None}


@unittest.skipUnless(shutil.which("git"), "needs git")
class OffsiteCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        self.c1 = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "two")
        self.c2 = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_verify(self, archive: FakeArchive, max_age: float = 14.0) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = offsite.verify(self.repo, offsite.ORIGIN, max_age, 0, None, fetch=archive, now=lambda: NOW,
                                  sleep=lambda s: None)
        return code, buf.getvalue()

    def test_matching_snapshot_passes(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/main": self.c2}))
        self.assertEqual(code, 0, out)

    def test_snapshot_behind_main_passes_with_note(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/main": self.c1}))
        self.assertEqual(code, 0, out)
        self.assertIn("within RPO", out)

    def test_no_snapshot_fails(self) -> None:
        code, out = self.run_verify(FakeArchive(None))
        self.assertEqual(code, 1)
        self.assertIn("no snapshot", out)

    def test_partial_visit_fails(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/main": self.c2}, status="partial"))
        self.assertEqual(code, 1)
        self.assertIn("not 'full'", out)

    def test_stale_snapshot_fails(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/main": self.c2}, date="2026-10-01T00:00:00Z"))
        self.assertEqual(code, 1)
        self.assertIn("days old", out)

    def test_foreign_commit_fails(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/main": "f" * 40}))
        self.assertEqual(code, 1)
        self.assertIn("foreign history", out)

    def test_rewritten_main_fails(self) -> None:
        git(self.repo, "reset", "-q", "--hard", self.c1)
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "rewritten")
        code, out = self.run_verify(FakeArchive({"refs/heads/main": self.c2}))
        self.assertEqual(code, 1)
        self.assertIn("was rewritten", out)

    def test_missing_default_branch_fails(self) -> None:
        code, out = self.run_verify(FakeArchive({"refs/heads/other": self.c2}))
        self.assertEqual(code, 1)
        self.assertIn("no refs/heads/main", out)

    def test_pagination_reads_every_branch(self) -> None:
        branches = {f"refs/heads/b{i}": self.c1 for i in range(5)} | {"refs/heads/main": self.c2}
        archive = FakeArchive(branches)
        self.assertEqual(offsite.snapshot_branches("ab" * 20, archive), branches | {"HEAD": "refs/heads/main"})
        self.assertGreaterEqual(sum("/snapshot/" in u for _, u in archive.calls), 3)

    def test_default_branch_comes_from_snapshot_head(self) -> None:
        """Regression: a live run against a repository whose default branch is master failed with
        'no refs/heads/main' because the default branch was hard-coded."""
        git(self.repo, "branch", "-m", "main", "master")
        archive = FakeArchive({"refs/heads/master": self.c2})
        archive.head = "refs/heads/master"
        code, out = self.run_verify(archive)
        self.assertEqual(code, 0, out)
        self.assertIn('"default_branch": "refs/heads/master"', out)

    def test_remote_tracking_branches_count_as_heads(self) -> None:
        git(self.repo, "update-ref", "refs/remotes/origin/feature", self.c1)
        git(self.repo, "update-ref", "refs/remotes/origin/HEAD", self.c2)
        refs = offsite.local_refs(self.repo)
        self.assertEqual(refs["refs/heads/feature"], self.c1)
        self.assertNotIn("refs/heads/HEAD", refs)

    def test_request_save_posts_to_the_save_endpoint(self) -> None:
        archive = FakeArchive({"refs/heads/main": self.c2})
        self.assertEqual(offsite.request_save(offsite.ORIGIN, archive)["save_request_status"], "accepted")
        self.assertEqual(archive.calls[0][0], "POST")
        self.assertIn("/origin/save/git/url/https://github.com/HUIIIM/Miao/", archive.calls[0][1])


if __name__ == "__main__":
    unittest.main()
