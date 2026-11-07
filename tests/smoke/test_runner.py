"""Smoke verdicts through the real production CLI, never stubbed checks."""

import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest


def test_committed_cs_expectation_accepts_explicit_unsupported(smoke_checkout):
    """Rule: D46 keeps CS refused/unsupported, but its CLI must actually run (CLI seam)."""
    expectations = json.loads((Path(__file__).parent / "expectations.json").read_text(encoding="utf-8"))
    assert expectations == {"HEALTH-S1": "released", "CS-S1": "refused"}
    sha = smoke_checkout.commit(cs=expectations["CS-S1"])
    kit = smoke_checkout.kit()
    actual = smoke_checkout.cs_cli(kit)
    assert actual.returncode == 2
    assert actual.stdout == ""
    assert actual.stderr == (
        "pets-release run: run supports only HEALTH-S1 in this build; the CS-S1 release needs ticket 23 "
        "and its search is follow-up #96\n"
    )
    smoke_checkout.run(kit)
    cs = smoke_checkout.record(sha)["scenarios"]["CS-S1"]
    assert cs["expected"] == "refused"
    assert set(cs["steps"]) == {"run"}
    assert cs["steps"]["run"]["status"] == "completed"
    assert cs["steps"]["run"]["exitCode"] == 2
    assert cs["error"] is None
    assert cs["pass"] is True
    assert cs["gate"] is None  # unsupported is not a fabricated gate pass
    assert not list((smoke_checkout.output / sha).glob("attempt-*/CS-S1"))


@pytest.mark.parametrize("fault", ["bare-exit-two", "missing-run-cli", "extra-stdout",
                                   "cs-process-error", "cs-planted-release", "cs-planted-scoring"])
def test_cs_unsupported_does_not_accept_crashes_errors_or_planted_outputs(smoke_checkout, fault):
    """Rule: only the exact observed unsupported outcome is allowed, never unknowns (CLI seam)."""
    run_cli = smoke_checkout.path / "src/pets_release/run/cli.py"
    if fault == "bare-exit-two":
        run_cli.write_text("raise SystemExit(2)\n", encoding="utf-8")
    elif fault == "missing-run-cli":
        run_cli.unlink()
    elif fault == "extra-stdout":
        source = run_cli.read_text(encoding="utf-8")
        run_cli.write_text(source.replace("from __future__ import annotations",
                                         "from __future__ import annotations\nprint('synthetic diagnostic')", 1),
                           encoding="utf-8")
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), fault=fault if fault.startswith("cs-") else None)
    record = smoke_checkout.record(sha)
    cs = record["scenarios"]["CS-S1"]
    if fault == "cs-process-error":
        assert cs["steps"]["run"]["status"] == "error"
        assert cs["steps"]["run"]["exitCode"] is None
    else:
        assert cs["steps"]["run"]["status"] == "completed"
        assert cs["steps"]["run"]["exitCode"] == 2
    assert cs["error"] == "run-unknown"
    assert cs["pass"] is False
    assert record["pass"] is False
    assert result.returncode == 1


def test_cs_unsupported_cannot_satisfy_a_released_expectation(smoke_checkout):
    """Rule: unsupported is permitted only by the committed refused expectation (CLI seam)."""
    sha = smoke_checkout.commit(cs="released")
    smoke_checkout.run(smoke_checkout.kit())
    cs = smoke_checkout.record(sha)["scenarios"]["CS-S1"]
    assert cs["steps"]["run"]["exitCode"] == 2
    assert cs["error"] == "run-unknown"
    assert cs["pass"] is False


def test_released_expectation_refuses_at_the_real_gate(smoke_checkout):
    """Rule: gate refusal cannot satisfy a committed released expectation (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(card=True))
    record = smoke_checkout.record(sha)
    assert result.returncode == 1
    assert record["pass"] is False
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 1
    assert health["failures"]["rescan.payment-cards"] >= 1
    assert health["pass"] is False


def test_planted_record_and_release_do_not_replace_fresh_cli_checks(smoke_checkout):
    """Rule: another SHA's smoke/release cannot satisfy this SHA (CLI seam)."""
    old_sha = smoke_checkout.commit()
    kit = smoke_checkout.kit()
    smoke_checkout.run(kit)
    assert smoke_checkout.record(old_sha)["scenarios"]["HEALTH-S1"]["pass"] is True
    new_sha = smoke_checkout.commit()
    planted = smoke_checkout.output / new_sha
    planted.mkdir()
    shutil.copyfile(smoke_checkout.output / old_sha / "smoke.json", planted / "smoke.json")
    release = next((smoke_checkout.output / old_sha).glob("attempt-*/HEALTH-S1"))
    shutil.copytree(release, planted / "HEALTH-S1")
    smoke_checkout.plant_card(kit)
    result = smoke_checkout.run(kit)
    record = smoke_checkout.record(new_sha)
    assert result.returncode == 1
    assert record["sha"] == new_sha
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 1  # actual gate refusal, not reused or existing-out error
    assert health["failures"]["rescan.payment-cards"] >= 1
    assert record["pass"] is False


def test_refused_expectation_cannot_release(smoke_checkout):
    """Rule: an unexpected release is a smoke failure, even with a clean gate (CLI seam)."""
    sha = smoke_checkout.commit(health="refused")
    result = smoke_checkout.run(smoke_checkout.kit())
    health = smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 0
    assert result.returncode == 1
    assert health["pass"] is False


def test_generic_expected_refusal_accepts_real_gate_failure(smoke_checkout):
    """Rule: refusal is generic, confirmed by real failing gate counts (CLI seam)."""
    sha = smoke_checkout.commit(health="refused")
    smoke_checkout.run(smoke_checkout.kit(card=True))
    health = smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 1
    assert health["failures"]["rescan.payment-cards"] > 0
    assert health["pass"] is True
    assert health["error"] is None
    assert not list((smoke_checkout.output / sha).glob("attempt-*/HEALTH-S1"))


@pytest.mark.parametrize("expected", ["released", "refused"])
def test_exit_two_is_unknown_for_every_expectation(smoke_checkout, expected):
    """Rule: a real CLI usage/state error is never a release or refusal (CLI seam)."""
    sha = smoke_checkout.commit(health=expected)
    result = smoke_checkout.run(smoke_checkout.kit(), fault="existing-run-output")
    assert smoke_checkout.observation() == {}
    record = smoke_checkout.record(sha)
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 2
    assert health["error"] == "run-unknown"
    assert health["pass"] is False
    assert record["pass"] is False
    assert result.returncode == 1


def test_release_runs_both_verify_tiers_dashboard_and_checks_aggregates(smoke_checkout):
    """Rule: a release needs all four real CLI steps plus measured privacy/utility (CLI seam)."""
    sha = smoke_checkout.commit()
    smoke_checkout.run(smoke_checkout.kit())
    record = smoke_checkout.record(sha)
    health = record["scenarios"]["HEALTH-S1"]
    assert set(health["steps"]) == {"run", "verify-limited", "verify-full", "dashboard"}
    assert all(s["exitCode"] == 0 and s["elapsedSeconds"] >= 0 for s in health["steps"].values())
    assert health["gate"]["passed"] > 0
    assert health["gate"]["failed"] == 0
    assert health["personK"]["minK"] >= health["personK"]["requiredK"] == 5
    assert health["purpose"] and all(t["pass"] for t in health["purpose"].values())
    assert health["dashboardWritten"] is True
    assert health["pass"] is True
    assert record["toolRevision"] == sha
    assert record["inputs"]["HEALTH-S1"]
    assert "run" in record["scenarios"]["CS-S1"]["steps"]


def test_default_smoke_does_not_require_measured_delivery(smoke_checkout):
    """Rule: D34 defaults run only plain HEALTH-S1 and unsupported CS-S1 (CLI seam)."""
    (smoke_checkout.path / "src/pets_release/measure/wire.py").unlink()
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit())
    record = smoke_checkout.record(sha)
    assert record["scenarios"]["HEALTH-S1"]["pass"] is True
    assert record["scenarios"]["CS-S1"]["steps"]["run"]["exitCode"] == 2
    assert record["scenarios"]["CS-S1"]["pass"] is True
    assert record["delivery"]["HEALTH-S1"] == {"status": "not-requested", "pass": None}
    assert smoke_checkout.validate(record) == 0
    for invalid_verdict in (True, False):
        forged = deepcopy(record)
        forged["delivery"]["HEALTH-S1"]["pass"] = invalid_verdict
        assert smoke_checkout.validate(forged) == 1
    assert not list((smoke_checkout.output / sha).glob("attempt-*/measured"))
    assert record["pass"] is True
    assert result.returncode == 0


def test_default_timeout_has_margin_beyond_observed_d34_runtime(smoke_checkout):
    """Rule: the default budget covers the observed 713-second D34 path with margin (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), fault="advance-clock-800")
    assert smoke_checkout.observation() == {"advancedSeconds": 800}
    record = smoke_checkout.record(sha)
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["status"] == "completed"
    assert all(step["exitCode"] == 0 for step in health["steps"].values())
    assert record["pass"] is True
    assert result.returncode == 0


def test_cli_generated_record_is_canonical_and_closed_at_every_level(smoke_checkout):
    """Rule: content-free records reject unknown keys, including nested ones (CLI seam)."""
    sha = smoke_checkout.commit()
    smoke_checkout.run(smoke_checkout.kit())
    record = smoke_checkout.record(sha)
    assert smoke_checkout.validate(record) == 0  # actual producer, not a hand-built writer/reader pair
    paths = [(), ("delivery", "HEALTH-S1"), ("scenarios", "HEALTH-S1"),
             ("scenarios", "HEALTH-S1", "steps", "run"),
             ("scenarios", "HEALTH-S1", "gate"), ("scenarios", "HEALTH-S1", "personK"),
             ("scenarios", "HEALTH-S1", "purpose", "H-U2")]
    outcomes = []
    for path in paths:
        planted = deepcopy(record)
        target = planted
        for key in path:
            target = target[key]
        target["unknown"] = True
        outcomes.append(smoke_checkout.validate(planted))
    assert outcomes == [1] * len(paths)
    raw = (smoke_checkout.output / sha / "smoke.json").read_bytes()
    assert raw == json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                             allow_nan=False).encode("utf-8")


def test_timed_out_cli_is_not_an_expected_refusal_or_pass(smoke_checkout):
    """Rule: an expired time budget is unknown, never a refusal/pass (CLI seam, real process)."""
    sha = smoke_checkout.commit(health="refused")
    result = smoke_checkout.run(smoke_checkout.kit(), "--timeout", "0.001")
    health = smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]
    assert result.returncode == 1
    assert health["steps"]["run"]["exitCode"] is None
    assert health["steps"]["run"]["status"] == "timeout"
    assert health["pass"] is False


def test_dirty_expectations_cannot_certify_a_committed_sha(smoke_checkout):
    """Rule: identity comes from the commit; a dirty checkout cannot mint SHA evidence (CLI seam)."""
    sha = smoke_checkout.commit()
    (smoke_checkout.path / "tests/smoke/expectations.json").write_text(
        '{"HEALTH-S1":"refused","CS-S1":"refused"}', encoding="utf-8")
    result = smoke_checkout.run(smoke_checkout.kit())
    health = smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]
    assert health["expected"] == "released"
    assert health["pass"] is False
    assert health["error"] == "dirty-checkout"
    assert result.returncode == 1


def test_missing_kit_writes_failed_record_not_stale_evidence(smoke_checkout):
    """Rule: unavailable kit leaves an explicit failed record (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.path / "missing-kit")
    assert result.returncode == 1
    record = smoke_checkout.record(sha)
    assert record["pass"] is False
    assert record["scenarios"]["HEALTH-S1"]["error"] == "kit-unavailable"


def test_requested_revision_must_match_actual_head(smoke_checkout):
    """Rule: a planted SHA selector cannot bind fresh CLI output to a different revision (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), "--sha", "0" * 40)
    health = smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]
    assert health["pass"] is False
    assert health["error"] == "revision-mismatch"
    assert result.returncode == 1


def test_head_change_during_run_invalidates_every_lane(smoke_checkout):
    """Rule: completion must recheck HEAD, even after a real passing release (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), "--measured-delivery", fault="head-drift")
    assert smoke_checkout.observation() == {}
    assert smoke_checkout.git("rev-parse", "HEAD") != sha
    record = smoke_checkout.record(sha)
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["verify-full"]["exitCode"] == 0
    assert health["gate"]["passed"] > 0
    for lane in [*record["scenarios"].values(), *record["delivery"].values()]:
        assert lane["error"] == "identity-changed"
        assert lane["pass"] is False
    assert record["sha"] == sha
    assert record["pass"] is False
    assert result.returncode == 1


def test_interruption_leaves_atomically_invalidated_evidence(smoke_checkout):
    """Rule: replace stale evidence atomically before work, even on abrupt exit (CLI seam)."""
    sha = smoke_checkout.commit()
    kit = smoke_checkout.kit()
    smoke_checkout.run(kit, "--measured-delivery")
    assert smoke_checkout.record(sha)["scenarios"]["HEALTH-S1"]["pass"] is True
    result = smoke_checkout.run(kit, "--measured-delivery", fault="interrupt-after-invalidation")
    assert result.returncode == 86
    record = smoke_checkout.record(sha)
    assert record["pass"] is False
    assert all(lane["pass"] is False for lane in [*record["scenarios"].values(),
                                                *record["delivery"].values()])
    assert smoke_checkout.validate(record) == 0
    # At the atomic rename boundary the old bytes still exist and the complete,
    # canonical failed replacement is ready. Direct writes cannot satisfy this.
    assert smoke_checkout.observation() == {
        "previousHealthPassed": True,
        "pendingPassed": False,
        "pendingScenarioPasses": [False, False],
        "canonical": True,
    }


def test_planted_wrong_tool_revision_is_rejected_before_verification(smoke_checkout):
    """Rule: the released manifest must bind to this SHA, not another revision (CLI seam)."""
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), fault="wrong-manifest-revision")
    assert smoke_checkout.observation() == {}
    record = smoke_checkout.record(sha)
    health = record["scenarios"]["HEALTH-S1"]
    assert health["steps"]["run"]["exitCode"] == 0
    assert health["gate"]["passed"] > 0
    assert health["error"] == "missing-or-invalid-step"
    assert all(health["steps"][name]["status"] == "not-run"
               for name in ("verify-limited", "verify-full", "dashboard"))
    assert health["pass"] is False
    assert record["pass"] is False
    assert result.returncode == 1


def test_linked_evidence_directory_cannot_redirect_records(smoke_checkout):
    """Rule: planted symlink/junction evidence directories must fail before writes (CLI seam)."""
    sha = smoke_checkout.commit()
    smoke_checkout.output.mkdir()
    target = smoke_checkout.output.parent / "planted-target"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    evidence = smoke_checkout.output / sha
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(evidence), str(target)],
                       capture_output=True, check=True, timeout=30)
    else:
        evidence.symlink_to(target, target_is_directory=True)
    result = smoke_checkout.run(smoke_checkout.path / "missing-kit")
    assert result.returncode == 1
    assert "evidence directory is a link" in result.stdout
    assert sorted(path.name for path in target.iterdir()) == ["sentinel.txt"]
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("missing", [False, True], ids=["errored-measured-cli", "missing-measured-cli"])
def test_measured_delivery_is_required_even_when_plain_release_passes(smoke_checkout, missing):
    """Rule: missing/errored measure.wire cannot hide behind a plain release (real CLI seam)."""
    if missing:
        (smoke_checkout.path / "src/pets_release/measure/wire.py").unlink()
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit(), "--measured-delivery")
    record = smoke_checkout.record(sha)
    assert record["scenarios"]["HEALTH-S1"]["pass"] is True
    assert "delivery" in record, "the measured delivery CLI must actually run"
    delivery = record["delivery"]["HEALTH-S1"]
    assert delivery.get("status") != "not-requested", "requested measured delivery must execute"
    assert delivery["steps"]["run"]["status"] == "completed"
    assert delivery["steps"]["run"]["exitCode"] == (1 if missing else 2)
    assert delivery["pass"] is False
    assert delivery["error"] is not None
    assert record["pass"] is False
    assert result.returncode == 1
