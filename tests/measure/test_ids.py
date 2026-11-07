"""One ID set: the measurer, the fixture manifest and the story-kit numbers template must agree."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pets_release.measure import measure
from pets_release.measure.ids import (
    BASELINE_METRICS,
    PERSON_K_IDS,
    PRIVACY_IDS,
    is_baseline_metric_id,
    is_privacy_component_id,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs" / "story-kit" / "numbers-template.csv"
FIXTURE = ROOT / "tests" / "fixtures" / "manifest" / "release" / "privacy_manifest.json"
SCENARIO = "TEST-S1"


def _template_paths() -> list[list[str]]:
    with TEMPLATE.open(encoding="utf-8", newline="") as f:
        return [r["manifest_key_path"].split(".") for r in csv.DictReader(f)
                if r["manifest_key_path"].startswith("measured.")]


def test_every_measured_path_in_the_story_kit_template_uses_a_measurer_id():
    paths = _template_paths()
    assert paths, "template has no measured.* rows"
    for p in paths:
        section = p[1]
        if section == "privacy":  # measured.privacy.<before|after>.<component>
            assert p[2] in ("before", "after") and ".".join(p[3:]) in (*PRIVACY_IDS, *PERSON_K_IDS), p
        elif section == "baselines":  # measured.baselines.<B0|B2|B2-k>.<metric>
            assert p[2] in ("B0", "B2", "B2-k") and is_baseline_metric_id(".".join(p[3:])), p
        elif section == "utility":  # measured.utility.<before|after>.<kit task id>
            assert p[2] in ("before", "after") and len(p) == 4, p
        elif section == "search":
            continue
        else:
            pytest.fail(f"unknown measured section in template: {p}")


def test_fixture_manifest_uses_only_measurer_ids():
    measured = json.loads(FIXTURE.read_text(encoding="utf-8"))["measured"]
    comps = [c["component"] for c in measured["privacy"]["components"]]
    assert comps and all(is_privacy_component_id(c) for c in comps), comps
    metrics = [r["metric"] for r in measured["baselines"]["rows"]]
    assert metrics and all(is_baseline_metric_id(m) for m in metrics), metrics


def test_template_privacy_ids_exist_in_the_fixture_manifest():
    measured = json.loads(FIXTURE.read_text(encoding="utf-8"))["measured"]
    comps = {c["component"] for c in measured["privacy"]["components"]}
    metrics = {r["metric"] for r in measured["baselines"]["rows"]}
    for p in _template_paths():
        mid = ".".join(p[3:])
        if p[1] == "privacy" and mid not in PERSON_K_IDS:  # person-k comes from the run, not the fixture
            assert mid in comps, p
        elif p[1] == "baselines" and not mid.startswith("task."):  # per-task rows depend on the scenario
            assert mid in metrics, p


def test_measurer_output_uses_the_same_ids_and_the_template_aggregates(args):
    block = measure(SCENARIO, **args)
    comps = [c["component"] for c in block["privacy"]["components"]]
    assert all(is_privacy_component_id(c) for c in comps)
    assert "privacy" in comps  # k_below_5_share / linkage_reid appear when the kit reports them (kit test)
    metrics = {r["metric"] for r in block["baselines"]["rows"]}
    assert all(is_baseline_metric_id(m) for m in metrics)
    assert set(BASELINE_METRICS) <= metrics


def test_id_sets_are_disjoint_and_stable():
    assert not set(PRIVACY_IDS) & set(PERSON_K_IDS)
    assert PRIVACY_IDS == ("privacy", "k_below_5_share", "linkage_reid")
