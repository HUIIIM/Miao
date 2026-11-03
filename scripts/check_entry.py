#!/usr/bin/env python3
"""Check every experiment entry against the rule in README.md ("What an entry needs").

    python3 scripts/check_entry.py                      # check experiments/ (CI runs this)
    python3 scripts/check_entry.py --root path/to/repo  # check another checkout
    python3 scripts/check_entry.py --write-manifest experiments/2026-11-01-my-test

An entry is a directory experiments/YYYY-MM-DD-slug/ (a real calendar date) that holds:

  README.md   at least one paragraph of prose saying what was tried and why,
              not the template's placeholder text
  run.sh | run.py | *.ipynb   the runnable minimal loop, not the template's stub
  output/     the real output: at least one non-empty file; placeholders such as
              .gitkeep do not count
  run.json    the run manifest (schema below); every file in output/ is listed
              with its sha256, and nothing else is listed

No file or directory in an entry may be a symbolic link: evidence must be the
committed bytes, not a pointer to something outside the entry.

run.json, schema_version 1:

  required  schema_version (1), command (non-empty str), started_at (ISO-8601
            date-time with a timezone), duration_s (finite number >= 0),
            environment (object), status ("works" | "failed" | "superseded"),
            outputs ({relative path: sha256})
  optional  code_commit, model (a version id: must contain a digit and must not
            be a "latest" alias), seed, tokens, cost_usd and max_cost_usd
            (finite numbers >= 0), superseded_by

Directories whose name starts with "_" or "." (for example _template) are skipped.
Standard library only. Python 3.10+; CI runs the tests on 3.10 and 3.13.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "experiments" / "_template"
NAME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ENTRY_POINTS = ("run.sh", "run.py")
PLACEHOLDERS = {".gitkeep", ".keep", ".gitignore"}
STATUSES = {"works", "failed", "superseded"}
REQUIRED: dict[str, tuple[type, ...]] = {
    "schema_version": (int,),
    "command": (str,),
    "started_at": (str,),
    "duration_s": (int, float),
    "environment": (dict,),
    "status": (str,),
    "outputs": (dict,),
}
MIN_PARAGRAPH = 40  # characters of prose; a heading or a one-word stub is not an explanation


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def is_number(value: Any) -> bool:
    """True for a finite int or float; bool, NaN, infinity and strings are not numbers here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def symlinks(entry: Path) -> list[str]:
    found = [entry] if entry.is_symlink() else []
    found += [p for p in entry.rglob("*") if p.is_symlink()]
    return sorted(p.relative_to(entry.parent).as_posix() for p in found)


def output_files(entry: Path) -> dict[str, Path]:
    """Regular files under output/, keyed by their path relative to the entry. Symlinks are excluded."""
    out = entry / "output"
    if out.is_symlink() or not out.is_dir():
        return {}
    return {
        p.relative_to(entry).as_posix(): p
        for p in sorted(out.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


def prose_paragraphs(text: str) -> list[str]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line for line in block.strip().splitlines() if line.strip()]
        if not lines or lines[0].lstrip().startswith(("#", "```", "|", "-", "*", ">", "<")):
            continue
        paragraphs.append(" ".join(line.strip() for line in lines))
    return paragraphs


def same_as_template(path: Path, name: str) -> bool:
    template = TEMPLATE / name
    return template.is_file() and path.is_file() and path.read_bytes() == template.read_bytes()


def valid_name(name: str) -> bool:
    m = NAME_RE.fullmatch(name)
    if not m:
        return False
    try:
        dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return False
    return True


def valid_timestamp(value: str) -> bool:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def load_manifest(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return None, "run.json is not UTF-8 text"
    except json.JSONDecodeError as e:
        return None, f"run.json is not valid JSON: {e}"
    if not isinstance(manifest, dict):
        return None, "run.json must be a JSON object"
    return manifest, None


def check_manifest(manifest: dict[str, Any], files: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    for key, types in REQUIRED.items():
        value = manifest.get(key)
        if key not in manifest:
            errors.append(f"run.json: missing '{key}'")
        elif not isinstance(value, types) or isinstance(value, bool):
            errors.append(f"run.json: '{key}' has the wrong type")

    if isinstance(manifest.get("schema_version"), int) and manifest["schema_version"] != 1:
        errors.append("run.json: schema_version must be 1")
    if isinstance(manifest.get("command"), str) and not manifest["command"].strip():
        errors.append("run.json: command must not be empty")
    if isinstance(manifest.get("started_at"), str) and not valid_timestamp(manifest["started_at"]):
        errors.append("run.json: started_at must be an ISO-8601 date-time with a timezone, e.g. 2026-11-01T10:00:00Z")
    if "duration_s" in manifest and isinstance(manifest["duration_s"], (int, float)) \
            and not isinstance(manifest["duration_s"], bool) \
            and not (is_number(manifest["duration_s"]) and manifest["duration_s"] >= 0):
        errors.append("run.json: duration_s must be a finite number >= 0")
    status = manifest.get("status")
    if isinstance(status, str) and status not in STATUSES:
        errors.append(f"run.json: status must be one of {sorted(STATUSES)}")
    if status == "superseded" and not manifest.get("superseded_by"):
        errors.append("run.json: status 'superseded' needs 'superseded_by'")

    for key in ("cost_usd", "max_cost_usd"):
        if key in manifest and not (is_number(manifest[key]) and manifest[key] >= 0):
            errors.append(f"run.json: {key} must be a finite number >= 0")
    cost, cap = manifest.get("cost_usd"), manifest.get("max_cost_usd")
    if isinstance(cost, (int, float)) and isinstance(cap, (int, float)) \
            and is_number(cost) and is_number(cap) and cost > cap and status == "works":
        errors.append("run.json: cost_usd exceeds max_cost_usd, so status cannot be 'works'")

    if "model" in manifest:
        model = manifest["model"]
        if not isinstance(model, str) or not re.search(r"\d", model) or "latest" in model.lower():
            errors.append("run.json: model must be a full version id (with a version number), not an alias")

    outputs = manifest.get("outputs")
    if isinstance(outputs, dict):
        for rel, digest in outputs.items():
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                errors.append(f"run.json: outputs['{rel}'] is not a lowercase sha256 hex digest")
            elif rel not in files:
                errors.append(f"run.json lists '{rel}' but no such regular file is committed in output/")
            elif sha256(files[rel]) != digest:
                errors.append(f"sha256 mismatch for '{rel}': the committed file is not the recorded output")
        for rel in files:
            if rel not in outputs:
                errors.append(f"'{rel}' is in output/ but not recorded in run.json outputs")
    return errors


def check_entry(entry: Path) -> list[str]:
    errors: list[str] = []
    if not valid_name(entry.name):
        errors.append("directory name must be YYYY-MM-DD-slug with a real date (lowercase, digits, hyphens)")
    for link in symlinks(entry):
        errors.append(f"'{link}' is a symbolic link: commit the real file instead")

    readme = entry / "README.md"
    if not readme.is_file():
        errors.append("missing README.md")
    elif same_as_template(readme, "README.md"):
        errors.append("README.md is still the template: describe what was tried and why")
    elif not any(len(p) >= MIN_PARAGRAPH for p in prose_paragraphs(readme.read_text(encoding="utf-8", errors="replace"))):
        errors.append(f"README.md needs a paragraph of at least {MIN_PARAGRAPH} characters saying what was tried and why")

    points = [entry / n for n in ENTRY_POINTS if (entry / n).is_file()] + sorted(entry.glob("*.ipynb"))
    if not points:
        errors.append("missing entry point (run.sh, run.py or a .ipynb notebook)")
    elif all(same_as_template(p, p.name) for p in points):
        errors.append("the entry point is still the template stub: commit the loop that produced the output")

    files = output_files(entry)
    evidence = {rel: p for rel, p in files.items() if p.name not in PLACEHOLDERS and p.stat().st_size > 0}
    if not evidence:
        errors.append("output/ has no real output: commit at least one non-empty file (placeholders like .gitkeep do not count)")

    manifest_path = entry / "run.json"
    if not manifest_path.is_file():
        errors.append("missing run.json")
        return errors
    manifest, problem = load_manifest(manifest_path)
    if manifest is None:
        errors.append(problem or "run.json could not be read")
        return errors
    return errors + check_manifest(manifest, files)


def entries(root: Path) -> list[Path]:
    base = root / "experiments"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir() and not p.name.startswith(("_", "."))]


def write_manifest(entry: Path) -> int:
    if not entry.is_dir():
        print(f"error: {entry} is not a directory", file=sys.stderr)
        return 2
    path = entry / "run.json"
    manifest: dict[str, Any] = {}
    if path.is_file():
        loaded, problem = load_manifest(path)
        if loaded is None:
            print(f"error: {path}: {problem}", file=sys.stderr)
            return 2
        manifest = loaded
    manifest["outputs"] = {rel: sha256(p) for rel, p in output_files(entry).items()}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest['outputs'])} output hashes to {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--write-manifest", type=Path, metavar="ENTRY_DIR",
                    help="record the sha256 of every file in ENTRY_DIR/output into its run.json")
    args = ap.parse_args(argv)

    if args.write_manifest:
        return write_manifest(args.write_manifest)

    found = entries(args.root)
    failed = 0
    for entry in found:
        try:
            errs = check_entry(entry)
        except OSError as exc:  # unreadable file: report it and keep checking the other entries
            errs = [f"could not read the entry: {exc}"]
        if errs:
            failed += 1
            print(f"FAIL {entry.relative_to(args.root)}")
            for err in errs:
                print(f"  - {err}")
        else:
            print(f"ok   {entry.relative_to(args.root)}")
    print(f"{len(found)} entr{'y' if len(found) == 1 else 'ies'} checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
