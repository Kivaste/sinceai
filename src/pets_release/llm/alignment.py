"""Alignment self-check: do the drafted purpose checks recover a packaged scenario's required tasks?

Content-free: it reports analysis IDs from the fixed vocabulary and counts, nothing else.
"""
from __future__ import annotations

from pets_release.policy import get_policy

PACKAGED = ("CS-S1", "HEALTH-S1")


class AlignmentError(ValueError):
    pass


def required_tasks(scenario: dict) -> list[str]:
    """The kit scenario's required utility tasks; only the packaged scenarios have a known vocabulary."""
    sid = scenario.get("id")
    if sid not in PACKAGED:
        raise AlignmentError("alignment is defined for the packaged scenarios only (HEALTH-S1, CS-S1)")
    tasks = scenario.get("utility_requirements")
    if not isinstance(tasks, list) or not tasks or not all(isinstance(t, str) for t in tasks):
        raise AlignmentError("the scenario lists no required tasks")
    known = set(get_policy(sid).purpose_checks)
    if not set(tasks) <= known:
        raise AlignmentError("the scenario requires a task the packaged policy does not know")
    return sorted(tasks)


def align(draft: dict, required: list[str]) -> dict:
    drafted = {c["id"] for c in draft["purposeChecks"]}
    req = sorted(set(required))
    recovered = [t for t in req if t in drafted]
    extra = sorted(drafted - set(req))
    return {
        "recovered": len(recovered),
        "required": len(req),
        "missing": [t for t in req if t not in drafted],
        "extra": extra,
        "summary": f"recovered {len(recovered)} of {len(req)} required analyses ({len(extra)} extra)",
    }
