"""Must-fix #111 through the real CLI (seam: `pets-release run`). Synthetic rows only.

Rule: the run path publishes only when the suppression report's ``withinBound`` is the bool ``True``. A missing
or non-bool ``withinBound`` is a refusal (exit 1, refusal report ``suppression:within-bound-missing``, no release
folder); it is never read as in-bound.

Failure rows (trigger -> wrong result before the fix):
  W1 suppression report without withinBound -> treated as in-bound, release published (exit 0)
  W2 withinBound is a non-bool truthy value -> treated as in-bound, release published (exit 0)

The production suppression step always sets the key today, so the trigger is planted by a fault-injection
wrapper around the real ``apply_suppression`` (it runs, then its report is edited) before the real CLI ``main``.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from run_helpers import ROOT, build_kit, coarse_qis, env, run_args

_INJECT = """
import sys
import pets_release.run.pipeline as P
_real = P.apply_suppression
MODE = sys.argv.pop(1)
def _planted(*a, **kw):
    released, finals, suppressed, sup = _real(*a, **kw)
    sup = dict(sup)
    if MODE == "missing":
        sup.pop("withinBound")
    elif MODE != "none":
        sup["withinBound"] = {"int": 1, "str": "false"}[MODE]
    return released, finals, suppressed, sup
P.apply_suppression = _planted
from pets_release.cli import main
raise SystemExit(main())
"""


def _run_planted(mode, kit, out):
    return subprocess.run([sys.executable, "-c", _INJECT, mode, *run_args(kit, out)], cwd=ROOT, env=env(),
                          capture_output=True, text=True, encoding="utf-8", check=False)


@pytest.fixture(scope="module")
def kit(tmp_path_factory):
    return build_kit(tmp_path_factory.mktemp("wb") / "kit", coarse_qis)  # within bound when unplanted


@pytest.mark.parametrize("mode", ["missing", "int", "str"])
def test_unproven_within_bound_refuses(kit, tmp_path, mode):
    out = tmp_path / "out" / "rel"
    proc = _run_planted(mode, kit, out)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    rep = json.loads((tmp_path / "out" / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert rep["status"] == "refused"
    assert rep["reasons"] == ["suppression:within-bound-missing"]


def test_wrapper_without_plant_still_releases(kit, tmp_path):
    """Control: the injection wrapper alone does not refuse, so the refusals above come from the planted value."""
    out = tmp_path / "out" / "rel"
    proc = _run_planted("none", kit, out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (out / "privacy_manifest.json").is_file()
