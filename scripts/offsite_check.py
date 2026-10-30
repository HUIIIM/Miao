#!/usr/bin/env python3
"""Off-site copy of this repository in the Software Heritage archive (SOTA OPS-1).

Software Heritage (https://www.softwareheritage.org) is a non-profit archive of public source code. Its copy
lives outside GitHub, anyone can check it through a public API, and the "vault" rebuilds a git repository from it.

    python3 scripts/offsite_check.py                 # verify the latest archived snapshot (read-only)
    python3 scripts/offsite_check.py --request-save  # ask the archive to take a new snapshot, then verify
    python3 scripts/offsite_check.py --wait 1800     # poll up to 30 minutes for a snapshot to appear

Verification passes only when all of these hold:
  * the archive has a snapshot of https://github.com/HUIIIM/Miao with status "full";
  * the snapshot is at most --max-age-days old (default 14, which is the off-site RPO);
  * every archived refs/heads/* and refs/tags/* commit exists in this clone (no foreign history);
  * the archived default branch (the snapshot's HEAD) is an ancestor of, or equal to, the current one
    (no rewritten history).
Newer commits that the archive has not seen yet are reported, not failed: that gap is the RPO.

Run it inside a full clone (`git fetch --unshallow` if needed). Standard library only; Python 3.10+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

API = "https://archive.softwareheritage.org/api/1"
ORIGIN = "https://github.com/HUIIIM/Miao"
DEFAULT_BRANCH = "refs/heads/main"
TRACKED = ("refs/heads/", "refs/tags/")


def get_json(url: str, method: str = "GET", timeout: int = 60) -> Any:
    req = urllib.request.Request(url, method=method, headers={"Accept": "application/json",
                                                              "User-Agent": "HUIIIM-Miao-offsite-check"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def origin_path(origin: str) -> str:
    return urllib.parse.quote(origin, safe=":/")


def request_save(origin: str, fetch: Callable[..., Any] = get_json) -> dict[str, Any]:
    result: dict[str, Any] = fetch(f"{API}/origin/save/git/url/{origin_path(origin)}/", method="POST")
    return result


def latest_visit(origin: str, fetch: Callable[..., Any] = get_json) -> dict[str, Any] | None:
    try:
        visit: dict[str, Any] = fetch(f"{API}/origin/{origin_path(origin)}/visit/latest/?require_snapshot=true")
    except urllib.error.HTTPError as e:
        # Only "origin not found" means "not archived yet"; any other 404 (a wrong API path) is a real error.
        reason = http_reason(e).lower() if e.code == 404 else ""
        if "origin" in reason and "not found" in reason:
            return None
        raise
    return visit


def http_reason(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read() or b"{}")
    except (ValueError, OSError):
        return ""
    return str(body.get("reason", "")) if isinstance(body, dict) else ""


def snapshot_branches(snapshot_id: str, fetch: Callable[..., Any] = get_json) -> dict[str, str]:
    """All branches of a snapshot as {ref: target}, following pagination. Revisions map to a commit sha;
    the HEAD alias maps to the ref it points at (the default branch)."""
    branches: dict[str, str] = {}
    start: str | None = None
    while True:
        url = f"{API}/snapshot/{snapshot_id}/?branches_count=1000"
        if start:
            url += "&branches_from=" + urllib.parse.quote(start, safe="")
        page: dict[str, Any] = fetch(url)
        for ref, target in (page.get("branches") or {}).items():
            if target and (target.get("target_type") == "revision" or ref == "HEAD"):
                branches[ref] = target["target"]
        start = page.get("next_branch")
        if not start:
            return branches


def local_refs(repo: Path) -> dict[str, str]:
    """Branches and tags of the clone. Remote-tracking branches (refs/remotes/origin/*, as in a CI checkout)
    count as refs/heads/* and win over a local branch of the same name."""
    out = subprocess.run(
        ["git", "-C", str(repo), "for-each-ref", "--format=%(objectname) %(refname)",
         *TRACKED, "refs/remotes/origin/"],
        check=True, capture_output=True, text=True,
    ).stdout
    local: dict[str, str] = {}
    remote: dict[str, str] = {}
    for line in out.splitlines():
        sha, ref = line.split(" ", 1)
        if ref.startswith("refs/remotes/origin/"):
            if ref != "refs/remotes/origin/HEAD":
                remote["refs/heads/" + ref[len("refs/remotes/origin/"):]] = sha
        else:
            local[ref] = sha
    return {**local, **remote}


def git_has_commit(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True).returncode == 0


def git_is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0


def age_days(visit_date: str, now: dt.datetime) -> float:
    taken = dt.datetime.fromisoformat(visit_date.replace("Z", "+00:00"))
    return (now - taken).total_seconds() / 86400


def compare(
    archived: dict[str, str],
    current: dict[str, str],
    has_commit: Callable[[str], bool],
    is_ancestor: Callable[[str, str], bool],
    default_branch: str = DEFAULT_BRANCH,
) -> tuple[list[str], list[str]]:
    """Return (errors, notes) for an archived snapshot against the current repository."""
    errors: list[str] = []
    notes: list[str] = []
    tracked = {ref: sha for ref, sha in archived.items() if ref.startswith(TRACKED)}
    if default_branch not in tracked:
        errors.append(f"the archived snapshot has no {default_branch}")
    for ref, sha in sorted(tracked.items()):
        if ref not in current and ref != default_branch:
            notes.append(f"{ref} was archived but no longer exists here (deleted since the snapshot)")
        elif not has_commit(sha):
            errors.append(f"archived {ref} = {sha[:12]} is not a commit in this repository (history was replaced)")
    old, new = tracked.get(default_branch), current.get(default_branch)
    if old and new and old != new and has_commit(old):
        if is_ancestor(old, new):
            notes.append(f"{default_branch} moved on since the snapshot ({old[:12]} -> {new[:12]}): within RPO")
        else:
            errors.append(f"{default_branch} was rewritten: archived {old[:12]} is not an ancestor of {new[:12]}")
    for ref in sorted(set(current) - set(tracked)):
        notes.append(f"{ref} is newer than the snapshot and not archived yet")
    return errors, notes


def is_ready(visit: dict[str, Any] | None, not_before: dt.datetime | None) -> bool:
    if visit is None or visit.get("status") != "full":
        return False
    return not_before is None or dt.datetime.fromisoformat(visit["date"].replace("Z", "+00:00")) >= not_before


def verify(repo: Path, origin: str, max_age_days: float, wait_s: int, report: Path | None,
           fetch: Callable[..., Any] = get_json, now: Callable[[], dt.datetime] | None = None,
           sleep: Callable[[float], None] = time.sleep, not_before: dt.datetime | None = None) -> int:
    """Verify the latest full snapshot. With not_before (the time of a save request), wait up to wait_s for a
    snapshot taken after it; if none comes in time, verify the previous one and say so."""
    clock = now or (lambda: dt.datetime.now(dt.timezone.utc))
    deadline = clock() + dt.timedelta(seconds=wait_s)
    visit = latest_visit(origin, fetch)
    while not is_ready(visit, not_before) and clock() < deadline:
        sleep(60)
        visit = latest_visit(origin, fetch)
    result: dict[str, Any] = {"origin": origin, "checked_at": clock().isoformat(), "errors": [], "notes": []}
    if not_before is not None and visit is not None and visit.get("status") == "full" \
            and not is_ready(visit, not_before):
        result["notes"].append("no snapshot newer than the save request arrived in time; "
                               "verified the previous snapshot instead")
    if visit is None or not visit.get("snapshot"):
        result["errors"].append(f"Software Heritage has no snapshot of {origin} yet")
    elif visit.get("status") != "full":
        result["errors"].append(f"the latest visit is '{visit.get('status')}', not 'full'")
    else:
        age = age_days(visit["date"], clock())
        result.update(snapshot=f"swh:1:snp:{visit['snapshot']}", visit_date=visit["date"], age_days=round(age, 2))
        if age > max_age_days:
            result["errors"].append(f"the latest snapshot is {age:.1f} days old (limit {max_age_days})")
        archived = snapshot_branches(visit["snapshot"], fetch)
        default_branch = archived.pop("HEAD", DEFAULT_BRANCH)
        result["default_branch"] = default_branch
        result["archived_refs"] = {r: s for r, s in sorted(archived.items()) if r.startswith(TRACKED)}
        errors, notes = compare(archived, local_refs(repo), lambda s: git_has_commit(repo, s),
                                lambda a, b: git_is_ancestor(repo, a, b), default_branch)
        result["errors"] += errors
        result["notes"] += notes
    result["ok"] = not result["errors"]
    text = json.dumps(result, indent=2)
    print(text)
    if report:
        report.write_text(text + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--origin", default=ORIGIN)
    ap.add_argument("--request-save", action="store_true", help="ask Software Heritage to archive the origin now")
    ap.add_argument("--wait", type=int, default=0, metavar="SECONDS", help="poll this long for a full snapshot")
    ap.add_argument("--max-age-days", type=float, default=14.0)
    ap.add_argument("--report", type=Path, help="also write the JSON result to this file")
    args = ap.parse_args(argv)
    not_before = None
    if args.request_save:
        not_before = dt.datetime.now(dt.timezone.utc)
        saved = request_save(args.origin)
        print(json.dumps({k: saved.get(k) for k in ("save_request_status", "save_task_status",
                                                     "save_request_date", "id")}))
        if saved.get("save_request_status") == "rejected":
            print("error: Software Heritage rejected the save request", file=sys.stderr)
            return 1
    return verify(args.repo, args.origin, args.max_age_days, args.wait, args.report, not_before=not_before)


if __name__ == "__main__":
    sys.exit(main())
