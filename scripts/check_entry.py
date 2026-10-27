#!/usr/bin/env python3
"""Check every experiment entry against the rule in README.md ("What an entry needs").

    python3 scripts/check_entry.py                      # check experiments/ (CI runs this)
    python3 scripts/check_entry.py --root path/to/repo  # check another checkout
    python3 scripts/check_entry.py --write-manifest experiments/2026-11-01-my-test

An entry is a directory experiments/YYYY-MM-DD-slug/ that holds:

  README.md   at least one paragraph of prose saying what was tried and why
  run.sh | run.py | *.ipynb   the runnable minimal loop
  output/     the real output, at least one file
  run.json    the run manifest (schema below); every file in output/ is listed
              with its sha256, and nothing else is listed

run.json, schema_version 1:

  required  schema_version (1), command (str), started_at (ISO-8601 str),
            duration_s (number >= 0), environment (object), status
            ("works" | "failed" | "superseded"), outputs ({relative path: sha256})
  optional  code_commit, model (full version id, not an alias), seed,
            tokens, cost_usd, max_cost_usd, superseded_by

Directories whose name starts with "_" or "." (for example _template) are skipped.
Standard library only, so it runs anywhere Python 3.9+ is installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ENTRY_POINTS = ("run.sh", "run.py")
STATUSES = {"works", "failed", "superseded"}
REQUIRED = {
    "schema_version": int,
    "command": str,
    "started_at": str,
    "duration_s": (int, float),
    "environment": dict,
    "status": str,
    "outputs": dict,
}
MIN_PARAGRAPH = 40  # characters of prose; a heading or a one-word stub is not an explanation


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def output_files(entry: Path) -> dict[str, Path]:
    out = entry / "output"
    return {p.relative_to(entry).as_posix(): p for p in sorted(out.rglob("*")) if p.is_file()}


def has_paragraph(readme: Path) -> bool:
    text = readme.read_text(encoding="utf-8", errors="replace")
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if not lines or lines[0].lstrip().startswith(("#", "```", "|", "-", "*", ">")):
            continue
        if len(" ".join(lines)) >= MIN_PARAGRAPH:
            return True
    return False


def check_entry(entry: Path) -> list[str]:
    errors: list[str] = []
    if not NAME_RE.match(entry.name):
        errors.append("directory name must be YYYY-MM-DD-slug (lowercase, digits, hyphens)")

    readme = entry / "README.md"
    if not readme.is_file():
        errors.append("missing README.md")
    elif not has_paragraph(readme):
        errors.append(f"README.md needs a paragraph of at least {MIN_PARAGRAPH} characters saying what was tried and why")

    if not any((entry / n).is_file() for n in ENTRY_POINTS) and not any(entry.glob("*.ipynb")):
        errors.append("missing entry point (run.sh, run.py or a .ipynb notebook)")

    files = output_files(entry) if (entry / "output").is_dir() else {}
    if not files:
        errors.append("output/ is missing or empty: commit the real output")

    manifest_path = entry / "run.json"
    if not manifest_path.is_file():
        errors.append("missing run.json")
        return errors
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"run.json is not valid JSON: {e}")
        return errors
    if not isinstance(manifest, dict):
        errors.append("run.json must be a JSON object")
        return errors

    for key, typ in REQUIRED.items():
        if key not in manifest:
            errors.append(f"run.json: missing '{key}'")
        elif not isinstance(manifest[key], typ) or isinstance(manifest[key], bool):
            errors.append(f"run.json: '{key}' has the wrong type")
    if manifest.get("schema_version") not in (None, 1) and isinstance(manifest.get("schema_version"), int):
        errors.append("run.json: schema_version must be 1")
    if isinstance(manifest.get("duration_s"), (int, float)) and manifest["duration_s"] < 0:
        errors.append("run.json: duration_s must be >= 0")
    if isinstance(manifest.get("status"), str) and manifest["status"] not in STATUSES:
        errors.append(f"run.json: status must be one of {sorted(STATUSES)}")
    if manifest.get("status") == "superseded" and not manifest.get("superseded_by"):
        errors.append("run.json: status 'superseded' needs 'superseded_by'")
    cost, cap = manifest.get("cost_usd"), manifest.get("max_cost_usd")
    if isinstance(cost, (int, float)) and isinstance(cap, (int, float)) and cost > cap and manifest.get("status") == "works":
        errors.append("run.json: cost_usd exceeds max_cost_usd, so status cannot be 'works'")

    outputs = manifest.get("outputs")
    if isinstance(outputs, dict):
        for rel, digest in outputs.items():
            if not isinstance(digest, str) or not SHA256_RE.match(digest):
                errors.append(f"run.json: outputs['{rel}'] is not a lowercase sha256 hex digest")
            elif rel not in files:
                errors.append(f"run.json lists '{rel}' but the file is not in output/")
            elif sha256(files[rel]) != digest:
                errors.append(f"sha256 mismatch for '{rel}': the committed file is not the recorded output")
        for rel in files:
            if rel not in outputs:
                errors.append(f"'{rel}' is in output/ but not recorded in run.json outputs")
    return errors


def entries(root: Path) -> list[Path]:
    base = root / "experiments"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith(("_", "."))]


def write_manifest(entry: Path) -> None:
    path = entry / "run.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    manifest["outputs"] = {rel: sha256(p) for rel, p in output_files(entry).items()}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest['outputs'])} output hashes to {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--write-manifest", type=Path, metavar="ENTRY_DIR",
                    help="record the sha256 of every file in ENTRY_DIR/output into its run.json")
    args = ap.parse_args(argv)

    if args.write_manifest:
        write_manifest(args.write_manifest)
        return 0

    found = entries(args.root)
    failed = 0
    for entry in found:
        errs = check_entry(entry)
        if errs:
            failed += 1
            print(f"FAIL {entry.relative_to(args.root)}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"ok   {entry.relative_to(args.root)}")
    print(f"{len(found)} entr{'y' if len(found) == 1 else 'ies'} checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
