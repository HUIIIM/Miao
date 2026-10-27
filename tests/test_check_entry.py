"""Tests for scripts/check_entry.py. Run: python3 -m unittest discover -s tests -v"""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_entry", HERE.parent / "scripts" / "check_entry.py")
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
        self.assertTrue(any("not in output/" in e for e in check_entry.check_entry(entry)))

    def test_empty_output_fails(self):
        entry = make_entry(self.root, outputs={})
        (entry / "output" / "stdout.txt").unlink()
        self.assertTrue(any("output/ is missing or empty" in e for e in check_entry.check_entry(entry)))

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

    def test_gitignore_does_not_hide_experiment_output(self):
        """Regression: .gitignore once ignored *.out, coverage.*, build/ and dist/, which silently dropped
        committed evidence (README: "its real output, committed as evidence")."""
        patterns = [l.strip() for l in (HERE.parent / ".gitignore").read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
        for banned in ("*.out", "coverage.*", "build/", "dist/"):
            self.assertNotIn(banned, patterns)


if __name__ == "__main__":
    unittest.main()
