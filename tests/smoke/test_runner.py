"""Smoke verdicts through the real production CLI, never stubbed checks."""

import json
import shutil
from copy import deepcopy

import pytest


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


def test_cli_generated_record_is_canonical_and_closed_at_every_level(smoke_checkout):
    """Rule: content-free records reject unknown keys, including nested ones (CLI seam)."""
    sha = smoke_checkout.commit()
    smoke_checkout.run(smoke_checkout.kit())
    record = smoke_checkout.record(sha)
    assert smoke_checkout.validate(record) == 0  # actual producer, not a hand-built writer/reader pair
    paths = [(), ("scenarios", "HEALTH-S1"), ("scenarios", "HEALTH-S1", "steps", "run"),
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


@pytest.mark.parametrize("missing", [False, True], ids=["errored-measured-cli", "missing-measured-cli"])
def test_measured_delivery_is_required_even_when_plain_release_passes(smoke_checkout, missing):
    """Rule: missing/errored measure.wire cannot hide behind a plain release (real CLI seam)."""
    if missing:
        (smoke_checkout.path / "src/pets_release/measure/wire.py").unlink()
    sha = smoke_checkout.commit()
    result = smoke_checkout.run(smoke_checkout.kit())
    record = smoke_checkout.record(sha)
    assert record["scenarios"]["HEALTH-S1"]["pass"] is True
    assert "delivery" in record, "the measured delivery CLI must actually run"
    delivery = record["delivery"]["HEALTH-S1"]
    assert delivery["steps"]["run"]["status"] == "completed"
    assert delivery["steps"]["run"]["exitCode"] == (1 if missing else 2)
    assert delivery["pass"] is False
    assert delivery["error"] is not None
    assert record["pass"] is False
    assert result.returncode == 1
