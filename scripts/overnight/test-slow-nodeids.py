"""D62 regressions through real pytest collection; no product tests are changed."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SlowNodeidsCollection(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".scratch" / "fu153"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True, capture_output=True)
        tests = self.repo / "tests"
        (tests / "run").mkdir(parents=True)
        shutil.copyfile(ROOT / "tests" / "conftest.py", tests / "conftest.py")
        (tests / "slow_tests.txt").write_text("", encoding="utf-8")
        (tests / "run" / "test_sample.py").write_text(
            "import pytest\n@pytest.mark.parametrize('kind', ['a b', 'a'])\n"
            "def test_heavy(kind): pass\ndef test_small(): pass\n", encoding="utf-8",
        )
        (self.repo / "pytest.ini").write_text(
            "[pytest]\nmarkers =\n    slow: heavy\n    kit: real kit\n", encoding="utf-8",
        )
        self.list_path = tests / "slow_nodeids.txt"

    def collect(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, "-m", "pytest", "--rootdir", str(self.repo),
             "--collect-only", "-q", "-p", "no:cacheprovider", *args],
            cwd=cwd or self.repo,
            env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONUTF8="1", TZ="UTC"),
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )

    def test_listed_exact_id_is_slow_and_unlisted_ids_stay_fast(self):
        self.list_path.write_text("tests/run/test_sample.py::test_heavy[a b]\n", encoding="utf-8")
        result = self.collect("-m", "not slow")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2/3 tests collected", result.stdout)
        self.assertNotIn("::test_heavy[a b]\n", result.stdout)
        self.assertIn("::test_heavy[a]\n", result.stdout)
        self.assertIn("::test_small\n", result.stdout)
        full = self.collect()
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assertIn("3 tests collected", full.stdout)

    def test_stale_id_fails_collection_even_with_marker_deselection(self):
        self.list_path.write_text("tests/run/test_sample.py::test_deleted\n", encoding="utf-8")
        result = self.collect("-m", "not slow")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stale tests/slow_nodeids.txt", result.stdout + result.stderr)

    def test_deleted_module_is_reported_in_full_collection(self):
        self.list_path.write_text("tests/deleted/test_gone.py::test_old\n", encoding="utf-8")
        result = self.collect()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("tests/deleted/test_gone.py::test_old", result.stdout + result.stderr)

    def test_existing_deselected_id_is_not_reported_as_stale(self):
        self.list_path.write_text("tests/run/test_sample.py::test_heavy[a b]\n", encoding="utf-8")
        result = self.collect("-k", "small", "-m", "not slow")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1/3 tests collected", result.stdout)

    def test_out_of_scope_id_does_not_break_targeted_collection(self):
        self.list_path.write_text("tests/run/test_sample.py::test_deleted\n", encoding="utf-8")
        result = self.collect("tests/run/test_sample.py::test_small")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 test collected", result.stdout)

    def test_malformed_id_outside_tests_is_not_silently_out_of_scope(self):
        self.list_path.write_text("typo/test_sample.py::test_heavy\n", encoding="utf-8")
        result = self.collect("tests")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("invalid tests/slow_nodeids.txt ID", result.stdout + result.stderr)

    def test_deleted_committed_list_fails_despite_planted_cwd_list(self):
        self.list_path.write_text("", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "synthetic"],
                       check=True, capture_output=True)
        self.list_path.unlink()
        planted = self.repo / "planted"
        planted.mkdir()
        (planted / "slow_nodeids.txt").write_text("", encoding="utf-8")
        result = self.collect(str(self.repo / "tests"), cwd=planted)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("cannot read tests/slow_nodeids.txt", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
