"""The one metric / component ID set shared by the measurer, the fixture manifest and the story-kit
numbers template (`docs/story-kit/numbers-template.csv`). tests/measure/test_ids.py checks the agreement.

Utility task IDs are the kit's own (`H-U2`, `CS-U4`, ...). Privacy components are `PRIVACY_IDS`, the
`risk.<table>_<name>` detail rows, and `PERSON_K_IDS` (after only). Baseline metrics are `BASELINE_METRICS`
plus `task.<kit task id>`."""

from __future__ import annotations

# aggregate privacy component -> suffix of the kit's per-table risk key it is the worst (max) of
RISK_AGGREGATES = {
    "k_below_5_share": ": records with k<5",
    "linkage_reid": ": linkage re-identification",
}
PRIVACY_IDS = ("privacy", *RISK_AGGREGATES)
PERSON_K_IDS = ("person_k.below_k_share", "person_k.min", "person_k.persons")
RISK_PREFIX = "risk."
BASELINE_METRICS = ("privacy", "utility_mean", "composite", "worst_reid", "residual_identifiers")
TASK_BASELINE_PREFIX = "task."


def is_privacy_component_id(cid: str) -> bool:
    return cid in PRIVACY_IDS or cid in PERSON_K_IDS or cid.startswith(RISK_PREFIX)


def is_baseline_metric_id(mid: str) -> bool:
    return mid in BASELINE_METRICS or mid.startswith(TASK_BASELINE_PREFIX)
