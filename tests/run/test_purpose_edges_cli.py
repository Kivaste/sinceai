"""Issue #93 regressions at the CLI seam; synthetic inputs only."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from run_helpers import ROOT, build_kit, coarse_qis, env, run_args
from test_low_severity_risks import _plant
from test_verify_assertion_rerun import MANIFEST, resign

# Fault injection, not a passing substitute: execute the real adapter on the real
# synthetic tables, then make its before-result unavailable. Acceptance and refusal
# reporting are unmodified production code reached through the actual CLI dispatcher.
_PURPOSE_FAULT = """
import sys
import pets_release.kiteval as adapter
mode = sys.argv.pop(1)
real = adapter.purpose_checks
def fault(scenario, source, released, *, root):
    results = real(scenario, source, released, root=root)
    if mode == "empty":
        return []
    if source is released:
        if mode == "missing":
            return [r for r in results if r["id"] != "H-U4"]
        for r in results:
            if r["id"] == "H-U4":
                if mode in ("error", "not_answerable"):
                    r.update(status=mode, score=None)
                else:
                    r.update(status="ok", score={"null": None, "nan": float("nan"),
                                                 "inf": float("inf"), "string": "1.0"}[mode])
    return results
adapter.purpose_checks = fault
if mode == "empty":
    from dataclasses import replace
    import pets_release.policy as policy
    import pets_release.run.pipeline as pipeline
    real_policy = policy.get_policy
    def empty_policy(scenario):
        return replace(real_policy(scenario), purpose_checks=(), sacrifices=(), rung_sacrifices=(),
                       alt_floors={}, alt_floor_conditions={})
    policy.get_policy = pipeline.get_policy = empty_policy
from pets_release.cli import main
raise SystemExit(main())
"""


def _fault_cli(mode, *args):
    return subprocess.run([sys.executable, "-c", _PURPOSE_FAULT, mode, *args], cwd=ROOT, env=env(),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def test_suppression_sidecar_describes_the_purpose_recheck(released):
    """Seam: CLI run; a published sidecar must not say its measured purpose checks are unwired."""
    _, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out.parent / "rel.scoring" / "suppression_report.json").read_text(encoding="utf-8"))
    assert manifest["measured"]["utility"]["status"] == "measured"
    assert report["recheck"]["purposeChecks"] == (
        "run re-runs all purpose checks on full data before publication; scores in measured.utility"
    )


@pytest.mark.parametrize("mode,reason", [
    ("not_answerable", "not_answerable"), ("error", "error"), ("missing", "missing"),
    ("null", "error"), ("nan", "error"), ("inf", "error"), ("string", "error"),
])
def test_unavailable_before_score_refuses_run(tmp_path, mode, reason):
    """Seam: CLI run; even a sacrificed task needs a finite, successful before-score."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    out = tmp_path / "out" / "rel"
    proc = _fault_cli(mode, *run_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    report = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))
    assert f"purpose:H-U4:before:{reason}" in report["reasons"]
    assert "Traceback" not in proc.stderr


def test_unavailable_before_score_fails_full_verify(released):
    """Seam: CLI verify --full; the same before-side prerequisite is freshly re-proved."""
    kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    full = _fault_cli("not_answerable", "verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "purpose:H-U4:before:not_answerable" in full.stdout


def test_empty_purpose_task_set_refuses_run(tmp_path):
    """Seam: CLI run; zero enforced tasks is an explicit refusal, not acceptance or a traceback."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    out = tmp_path / "out" / "rel"
    proc = _fault_cli("empty", *run_args(kit, out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not out.exists()
    report_path = out.parent / "rel.scoring" / "refusal_report.json"
    assert report_path.is_file(), proc.stdout + proc.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["reasons"] == ["purpose:no-tasks"]
    assert "Traceback" not in proc.stderr


def test_empty_purpose_task_set_fails_full_verify(released):
    """Seam: CLI verify --full; an empty fresh task set must not pass vacuously."""
    kit, out, proc = released
    assert proc.returncode == 0, proc.stdout + proc.stderr
    full = _fault_cli("empty", "verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "purpose:no-tasks" in full.stdout


# Exercise a producer-scoped low-severity record using the REAL text.health scan.
# Only its registered identity/scope is adapted; no check or hit is replaced with
# a canned pass, and the original registry checks all remain enabled.
_RISK_CHECK = """
import os
import sys
from dataclasses import replace
from pets_release.checks import all_checks
from pets_release.checks.registry import register
health = next(c for c in all_checks() if c.name == "text.health")
names = [("edge.health-producer", "producer")]
if os.environ.get("EDGE_LONG_NAMES"):
    names = [("edge." + "q" * 58 + suffix, scope) for suffix, scope in (("a", "release"), ("b", "producer"))]
for name, scope in names:
    def scan(release, contract, context, name=name):
        result = health.run(release, contract, context)
        return replace(result, violations=tuple(replace(v, check=name) for v in result.violations))
    register(name=name, version=health.version, scope=scope, unit=health.unit,
             applies_to=health.applies_to)(scan)
from pets_release.cli import main
raise SystemExit(main())
"""


def _risk_cli(*args, long_names=False):
    return subprocess.run([sys.executable, "-c", _RISK_CHECK, *args], cwd=ROOT,
                          env=env({"EDGE_LONG_NAMES": "1"} if long_names else {}),
                          capture_output=True, text=True, encoding="utf-8", check=False)


def test_recipient_scope_does_not_parse_residual_risk_ids(tmp_path):
    """Seam: CLI run/verify; risk IDs are opaque, not a colon-delimited scope channel."""
    kit = build_kit(tmp_path / "kit", _plant)
    out = tmp_path / "out" / "rel"
    proc = _risk_cli(*run_args(kit, out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    producer = next(r for r in manifest["residualRisks"] if r["risk"] == "gate:edge.health-producer:HEALTH")
    producer["risk"] = "opaque-producer-risk"
    manifest["residualRisks"].sort(key=lambda r: r["risk"])
    (out / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    resign(out)
    limited = _risk_cli("verify", str(out))
    assert limited.returncode == 0, limited.stdout + limited.stderr
    assert "VERIFIED (limited)" in limited.stdout
    full = _risk_cli("verify", "--full", "--kit", str(kit), str(out))
    assert full.returncode == 1, full.stdout + full.stderr
    assert "residualRisks" in full.stdout and "opaque-producer-risk" in full.stdout


def test_long_check_names_have_distinct_reverifiable_risk_ids(tmp_path):
    """Seam: CLI run/verify; distinct full check identities must survive the 64-character risk-ID limit."""
    kit = build_kit(tmp_path / "kit", _plant)
    out = tmp_path / "out" / "rel"
    proc = _risk_cli(*run_args(kit, out), long_names=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    low = [r for r in manifest["residualRisks"] if r["kind"] == "gate_low_severity"]
    assert len(low) == 3
    assert len({r["risk"] for r in low}) == 3
    assert all(len(r["risk"]) <= 64 for r in low)
    limited = _risk_cli("verify", str(out), long_names=True)
    assert limited.returncode == 0, limited.stdout + limited.stderr
    full = _risk_cli("verify", "--full", "--kit", str(kit), str(out), long_names=True)
    assert full.returncode == 0, full.stdout + full.stderr
    release_risk = next(r for r in low if "edge." in r["rate"]["source"] and "(release scope)" in r["rate"]["source"])
    release_risk["rate"]["count"] += 1
    (out / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    resign(out)
    limited = _risk_cli("verify", str(out), long_names=True)
    assert limited.returncode == 1 and "residualRisks" in limited.stdout, limited.stdout + limited.stderr
