"""Smoke verdicts through the real production CLI, never stubbed checks."""

import json
import shutil


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
    assert smoke_checkout.run(kit).returncode == 0
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
