"""Baseline rows against the kit's own docs table. Skipped when the kit is absent (PETS_KIT, else the
conventions path). The literals are the 2-decimal HEALTH-S1 / CS-S1 rows of docs/BENCHMARK.md
(utility per sharing scenario: B0, B2, B2-k)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pets_release.measure import baseline_rows

_DEFAULT_KIT = Path(r"C:\Users\kivas\AI\sinceai-hackaton\Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)"
                    r"\TRUSTED_PETS_PROVING_GROUND_2026")
KIT = Path(os.environ.get("PETS_KIT") or _DEFAULT_KIT)

PUBLISHED = {  # scenario -> dataset, (B0, B2, B2-k) utility
    "HEALTH-S1": ("health", (1.00, 0.79, 0.40)),
    "CS-S1": ("customer_service", (1.00, 0.75, 0.75)),
}


@pytest.mark.kit
@pytest.mark.parametrize("scenario", sorted(PUBLISHED))
def test_baseline_utility_matches_published_table(scenario):
    if not (KIT / "results" / "benchmark.json").is_file():
        pytest.skip("challenge kit not available")
    dataset, expected = PUBLISHED[scenario]
    rows = {(r["baseline"], r["metric"]): r["value"] for r in baseline_rows(KIT, scenario, dataset)}
    got = tuple(round(rows[(b, f"utility.{scenario}")], 2) for b in ("B0", "B2", "B2-k"))
    assert got == expected
    assert all(0.0 <= rows[(b, "privacy")] <= 1.0 for b in ("B0", "B2", "B2-k"))
