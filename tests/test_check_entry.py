"""Tests for scripts/check_entry.py. Run: python3 -m unittest discover -s tests -v"""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_entry", HERE.parent / "scripts" / "check_entry.py")
assert spec is not None and spec.loader is not None
check_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_entry)

PARAGRAPH = "Tried a two-line prompt loop to see whether the model keeps a running total across turns."


def make_entry(root: Path, name="2026-11-01-sum-loop", **overrides) -> Path:
    entry = root / "experiments" / name
    (entry / "output").mkdir(parents=True)
    (entry / "README.md").write_text(f"# Sum loop\n\n{PARAGRAPH}\n", encoding="utf-8")
    (entry / "run.py").write_text("print(1 + 1)\n", encoding="utf-8")
    (entry / "output" / "stdout.txt").write_text("2\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "command": "python3 run.py > output/stdout.txt",
        "started_at": "2026-11-01T10:00:00Z",
        "duration_s": 0.04,
        "environment": {"python": "3.12.3"},
        "status": "works",
        "outputs": {"output/stdout.txt": hashlib.sha256(b"2\n").hexdigest()},
    }
    manifest.update(overrides)
    (entry / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    return entry


class CheckEntryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = check_entry.main(["--root", str(self.root)])
        return code, buf.getvalue()

    def test_valid_entry_passes(self):
        self.assertEqual(check_entry.check_entry(make_entry(self.root)), [])

    def test_no_experiments_directory_passes(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("0 entries checked", out)

    def test_template_directory_is_skipped(self):
        (self.root / "experiments" / "_template").mkdir(parents=True)
        code, _ = self.run_main()
        self.assertEqual(code, 0)

    def test_tampered_output_fails(self):
        entry = make_entry(self.root)
        (entry / "output" / "stdout.txt").write_text("3\n", encoding="utf-8")
        self.assertTrue(any("sha256 mismatch" in e for e in check_entry.check_entry(entry)))
        self.assertEqual(self.run_main()[0], 1)

    def test_unrecorded_output_fails(self):
        entry = make_entry(self.root)
        (entry / "output" / "extra.log").write_text("x", encoding="utf-8")
        self.assertTrue(any("not recorded" in e for e in check_entry.check_entry(entry)))

    def test_listed_but_missing_output_fails(self):
        entry = make_entry(self.root, outputs={
            "output/stdout.txt": hashlib.sha256(b"2\n").hexdigest(),
            "output/gone.txt": "0" * 64,
        })
        self.assertTrue(any("no such regular file" in e for e in check_entry.check_entry(entry)))

    def test_empty_output_fails(self):
        entry = make_entry(self.root, outputs={})
        (entry / "output" / "stdout.txt").unlink()
        self.assertTrue(any("no real output" in e for e in check_entry.check_entry(entry)))

    def test_heading_only_readme_fails(self):
        entry = make_entry(self.root)
        (entry / "README.md").write_text("# Sum loop\n\n- todo\n", encoding="utf-8")
        self.assertTrue(any("paragraph" in e for e in check_entry.check_entry(entry)))

    def test_missing_entry_point_fails(self):
        entry = make_entry(self.root)
        (entry / "run.py").unlink()
        self.assertTrue(any("entry point" in e for e in check_entry.check_entry(entry)))

    def test_notebook_counts_as_entry_point(self):
        entry = make_entry(self.root)
        (entry / "run.py").unlink()
        (entry / "loop.ipynb").write_text("{}", encoding="utf-8")
        self.assertEqual(check_entry.check_entry(entry), [])

    def test_bad_directory_name_fails(self):
        entry = make_entry(self.root, name="Sum Loop")
        self.assertTrue(any("YYYY-MM-DD-slug" in e for e in check_entry.check_entry(entry)))

    def test_missing_required_key_fails(self):
        entry = make_entry(self.root)
        manifest = json.loads((entry / "run.json").read_text())
        del manifest["command"]
        (entry / "run.json").write_text(json.dumps(manifest))
        self.assertIn("run.json: missing 'command'", check_entry.check_entry(entry))

    def test_invalid_json_fails(self):
        entry = make_entry(self.root)
        (entry / "run.json").write_text("{not json")
        self.assertTrue(any("not valid JSON" in e for e in check_entry.check_entry(entry)))

    def test_bad_status_fails(self):
        entry = make_entry(self.root, status="ok")
        self.assertTrue(any("status must be one of" in e for e in check_entry.check_entry(entry)))

    def test_superseded_needs_pointer(self):
        entry = make_entry(self.root, status="superseded")
        self.assertTrue(any("superseded_by" in e for e in check_entry.check_entry(entry)))

    def test_over_budget_cannot_be_works(self):
        entry = make_entry(self.root, cost_usd=2.5, max_cost_usd=1.0)
        self.assertTrue(any("exceeds max_cost_usd" in e for e in check_entry.check_entry(entry)))

    def test_over_budget_failed_run_is_allowed(self):
        entry = make_entry(self.root, cost_usd=2.5, max_cost_usd=1.0, status="failed")
        self.assertEqual(check_entry.check_entry(entry), [])

    # Regressions for the independent assessment of PR #6 (fe31c07): each case used to pass the checker.

    def test_untouched_template_copy_fails(self):
        entry = self.root / "experiments" / "2026-11-01-untouched"
        shutil.copytree(check_entry.TEMPLATE, entry)
        with redirect_stdout(io.StringIO()):
            check_entry.main(["--write-manifest", str(entry)])
        errors = check_entry.check_entry(entry)
        self.assertTrue(any("still the template" in e for e in errors))
        self.assertTrue(any("template stub" in e for e in errors))
        self.assertTrue(any("no real output" in e for e in errors))
        self.assertTrue(any("started_at" in e for e in errors))

    def test_gitkeep_alone_is_not_output(self):
        entry = make_entry(self.root, outputs={"output/.gitkeep": hashlib.sha256(b"").hexdigest()})
        (entry / "output" / "stdout.txt").unlink()
        (entry / "output" / ".gitkeep").write_bytes(b"")
        self.assertTrue(any("no real output" in e for e in check_entry.check_entry(entry)))

    def test_empty_file_alone_is_not_output(self):
        entry = make_entry(self.root, outputs={"output/stdout.txt": hashlib.sha256(b"").hexdigest()})
        (entry / "output" / "stdout.txt").write_bytes(b"")
        self.assertTrue(any("no real output" in e for e in check_entry.check_entry(entry)))

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_symlinked_output_file_fails(self):
        entry = make_entry(self.root)
        outside = self.root / "outside.txt"
        outside.write_text("2\n")
        (entry / "output" / "stdout.txt").unlink()
        (entry / "output" / "stdout.txt").symlink_to(outside)
        errors = check_entry.check_entry(entry)
        self.assertTrue(any("symbolic link" in e for e in errors))

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_symlinked_output_directory_fails(self):
        entry = make_entry(self.root)
        real = self.root / "real-output"
        shutil.move(str(entry / "output"), str(real))
        (entry / "output").symlink_to(real, target_is_directory=True)
        errors = check_entry.check_entry(entry)
        self.assertTrue(any("symbolic link" in e for e in errors))
        self.assertTrue(any("no real output" in e for e in errors))

    def test_nan_duration_fails(self):
        entry = make_entry(self.root)
        raw = (entry / "run.json").read_text().replace('"duration_s": 0.04', '"duration_s": NaN')
        (entry / "run.json").write_text(raw)
        self.assertTrue(any("duration_s must be a finite number" in e for e in check_entry.check_entry(entry)))

    def test_string_cost_cannot_bypass_cap(self):
        entry = make_entry(self.root, cost_usd="999", max_cost_usd=1.0)
        self.assertTrue(any("cost_usd must be a finite number" in e for e in check_entry.check_entry(entry)))

    def test_nan_cost_cannot_bypass_cap(self):
        entry = make_entry(self.root, max_cost_usd=1.0)
        raw = (entry / "run.json").read_text().rstrip("}") + ', "cost_usd": NaN}'
        (entry / "run.json").write_text(raw)
        self.assertTrue(any("cost_usd must be a finite number" in e for e in check_entry.check_entry(entry)))

    def test_impossible_dates_fail(self):
        for name in ("2026-13-45-x", "0000-00-00-x", "2026-02-30-x"):
            entry = make_entry(self.root, name=name)
            self.assertTrue(any("real date" in e for e in check_entry.check_entry(entry)), name)

    def test_trailing_newline_name_fails(self):
        self.assertFalse(check_entry.valid_name("2026-11-01-x\n"))

    def test_model_alias_fails(self):
        for model in ("latest", "claude-latest", "gpt"):
            entry = make_entry(self.root, name=f"2026-11-01-{model}", model=model)
            self.assertTrue(any("model must be a full version id" in e for e in check_entry.check_entry(entry)), model)

    def test_versioned_model_passes(self):
        self.assertEqual(check_entry.check_entry(make_entry(self.root, model="claude-opus-5-5")), [])

    def test_html_comment_is_not_a_paragraph(self):
        entry = make_entry(self.root)
        (entry / "README.md").write_text(f"# Sum loop\n\n<!-- {PARAGRAPH} -->\n")
        self.assertTrue(any("paragraph" in e for e in check_entry.check_entry(entry)))

    def test_placeholder_started_at_fails(self):
        for value in ("YYYY-MM-DDTHH:MM:SSZ", "2026-11-01T10:00:00", "yesterday"):
            entry = make_entry(self.root, name=f"2026-11-0{len(value) % 9 + 1}-t", started_at=value)
            self.assertTrue(any("started_at" in e for e in check_entry.check_entry(entry)), value)

    def test_non_utf8_manifest_is_reported_not_raised(self):
        entry = make_entry(self.root)
        (entry / "run.json").write_bytes(b"\xff\xfe{")
        self.assertIn("run.json is not UTF-8 text", check_entry.check_entry(entry))

    def test_write_manifest_missing_directory_returns_error(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(check_entry.main(["--write-manifest", str(self.root / "nope")]), 2)

    def test_write_manifest_on_array_json_returns_error(self):
        entry = make_entry(self.root)
        (entry / "run.json").write_text("[]")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(check_entry.main(["--write-manifest", str(entry)]), 2)

    def test_boolean_is_not_a_number(self):
        entry = make_entry(self.root, duration_s=True)
        self.assertIn("run.json: 'duration_s' has the wrong type", check_entry.check_entry(entry))

    def test_write_manifest_records_hashes(self):
        entry = make_entry(self.root, outputs={})
        with redirect_stdout(io.StringIO()):
            check_entry.main(["--write-manifest", str(entry)])
        self.assertEqual(check_entry.check_entry(entry), [])


class RepositoryTest(unittest.TestCase):
    def test_repository_entries_pass(self):
        root = HERE.parent
        failures = {e.name: check_entry.check_entry(e) for e in check_entry.entries(root)}
        self.assertEqual({k: v for k, v in failures.items() if v}, {})

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_gitignore_does_not_hide_experiment_output(self):
        """Regression: .gitignore once ignored *.out, coverage.*, build/ and dist/, which silently dropped
        committed evidence (README: "its real output, committed as evidence"). Ask git itself."""
        paths = [
            "experiments/2026-11-01-x/output/run.out",
            "experiments/2026-11-01-x/output/coverage.xml",
            "experiments/2026-11-01-x/output/build/log.txt",
            "experiments/2026-11-01-x/output/dist/model.bin",
            "experiments/2026-11-01-x/output/stdout.txt",
        ]
        result = subprocess.run(
            ["git", "-C", str(HERE.parent), "check-ignore", "--no-index", "--verbose", *paths],
            capture_output=True, text=True,
        )
        self.assertEqual(result.stdout, "", f"ignored by .gitignore: {result.stdout}")


if __name__ == "__main__":
    unittest.main()
