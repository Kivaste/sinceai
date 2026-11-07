"""Must-fix #118 through the real CLI (seam: `pets-release run` without `--plan`, the search path). Synthetic rows.

Rule: a PersonK the search cannot measure is a refusal, never a score: exit 1, no release folder, a refusal report
``search:no-acceptable-plan`` and an empty search log (no candidate was scored). It is never read as zero
shortfall, and the run does not end in an uncaught crash.

Failure row (trigger -> wrong result before the fix):
  P1 per-person k yields no PersonK during the search -> RuntimeError traceback out of `run` (exit 1 by crash),
     no refusal report, no search log

The production per-person k raises on every fail-closed condition today, so the missing result is planted by a
fault-injection wrapper that replaces ``risk.person_k_values`` (the boundary to ticket 11's check) before the real
CLI ``main``; the control case runs the same wrapper without the plant and releases.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from run_helpers import CREATED, ROOT, build_kit, env, grouped_qis

_INJECT = """
import sys
import pets_release.minimiser.risk as R
if sys.argv.pop(1) == "missing":
    R.person_k_values = lambda *a, **kw: None
from pets_release.cli import main
raise SystemExit(main())
"""


def _run(mode, kit, out):
    args = ["run", "--scenario", "HEALTH-S1", "--kit", str(kit), "--out", str(out), "--created", CREATED]
    return subprocess.run([sys.executable, "-c", _INJECT, mode, *args], cwd=ROOT, env=env(),
                          capture_output=True, text=True, encoding="utf-8", check=False)


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_kit(tmp_path_factory.mktemp("pk") / "kit", grouped_qis)  # the search releases when unplanted


def test_missing_person_k_refuses_through_run(kit, tmp_path):
    out = tmp_path / "out" / "rel"
    proc = _run("missing", kit, out)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr
    assert not out.exists()
    sc = tmp_path / "out" / "rel.scoring"
    rep = json.loads((sc / "refusal_report.json").read_text(encoding="utf-8"))
    assert rep["status"] == "refused" and rep["reasons"] == ["search:no-acceptable-plan"]
    log = [line for line in (sc / "search_log.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert log == []  # refused at the first candidate: nothing scored on an unmeasured PersonK


def test_wrapper_without_plant_still_releases(kit, tmp_path):
    """Control: the injection wrapper alone releases, so the refusal above comes from the planted PersonK."""
    out = tmp_path / "out" / "rel"
    proc = _run("none", kit, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "privacy_manifest.json").is_file()
