"""Alignment self-check: drafted purpose checks vs. the official required tasks of a packaged scenario."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_provider import FakeProvider

from pets_release.llm.alignment import AlignmentError, align, required_tasks

DRAFT = {"purposeChecks": [{"id": "H-U2", "reason": "a"}, {"id": "H-U4", "reason": "b"}, {"id": "H-U8", "reason": "c"}]}


def test_recovered_missing_and_extra_are_counted():
    r = align(DRAFT, ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"])
    assert (r["recovered"], r["required"]) == (3, 5)
    assert r["missing"] == ["H-U6", "H-U7"] and r["extra"] == []
    assert r["summary"] == "recovered 3 of 5 required analyses (0 extra)"


def test_extra_analyses_are_reported():
    r = align({"purposeChecks": [{"id": "H-U2", "reason": "a"}, {"id": "H-U1", "reason": "b"}]}, ["H-U2"])
    assert r["extra"] == ["H-U1"] and r["recovered"] == 1


def test_required_tasks_come_from_the_scenario_and_only_packaged_scenarios_qualify():
    scen = {"id": "HEALTH-S1", "utility_requirements": ["H-U8", "H-U2"]}
    assert required_tasks(scen) == ["H-U2", "H-U8"]
    with pytest.raises(AlignmentError):
        required_tasks({"id": "MOB-S1", "utility_requirements": ["M-U1"]})
    with pytest.raises(AlignmentError):
        required_tasks({"id": "HEALTH-S1", "utility_requirements": []})


def test_cli_self_check_reports_recovered_n_of_m(cli, make_kit, tmp_path):
    reply = {
        "recipient": "University research group",
        "trustLevel": "controlled_research",
        "purposeChecks": [{"id": "H-U2", "reason": "x"}, {"id": "H-U4", "reason": "y"}],
        "fieldsNeeded": [{"table": "ed_visits", "column": "when", "detail": "exact", "reason": "x"}],
    }
    provider = FakeProvider(tmp_path / "provider", reply=reply)
    try:
        kit = make_kit(scenarios=[{
            "id": "HEALTH-S1", "dataset": "health", "recipient": "A research group", "purpose": "Analyse stays",
            "utility_requirements": ["H-U2", "H-U4"],
        }])
        r = cli("draft-policy", "--align-with", "HEALTH-S1", "--kit", str(kit), "--allow-network",
                env=provider["env"])
    finally:
        provider.close()
    assert r.returncode == 0, r.stderr
    assert "recovered 2 of 2 required analyses" in r.stderr
    assert json.loads(r.stdout)["status"] == "draft"
