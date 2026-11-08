"""Purpose evaluation on full data: the publication prerequisite (``run``) and the fresh ``verify --full`` check.

One function, both paths. Every policy purpose check (plus any task the kit marks required) is run through the
kit-eval adapter's in-process tasks; "before" is the source scored against itself. A check is accepted when its
status is ``ok`` and it scores >= ``THRESHOLD``, or below that only for a policy-enumerated sacrifice at or above
its fixed floor. Error, not_answerable and missing are never waived. Scores and reason codes only; no values.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

THRESHOLD = 0.9
SOURCE = "kit-eval adapter in-process purpose checks on full data; before = source scored against itself"
_TASK_STATUS = ("ok", "error", "not_answerable")  # manifest measured.utility statuses


@dataclass(frozen=True)
class PurposeResult:
    tasks: tuple  # ({"task", "status", "before", "after"}, ...) sorted by task; status may be "missing"
    reasons: tuple  # content-free reason codes; empty means accepted

    @property
    def ok(self) -> bool:
        return not self.reasons


def _by_id(results) -> dict:
    return {r["id"]: r for r in results}


def _score(r):
    score = r.get("score") if r is not None and r.get("status") == "ok" else None
    return score if isinstance(score, float) and math.isfinite(score) else None


def evaluate(policy, source, released, *, root) -> PurposeResult:
    """Evaluate ``released`` ({table: DataFrame}) against ``source`` for ``policy``'s scenario. Never raises."""
    from pets_release.kiteval import counts_as_fail, purpose_checks

    try:
        after = _by_id(purpose_checks(policy.scenario, source, released, root=root))
        before = _by_id(purpose_checks(policy.scenario, source, source, root=root))
    except Exception:  # noqa: BLE001 - adapter text could carry values; keep the code only
        return PurposeResult((), ("purpose:unavailable",))
    enforced = sorted(set(policy.purpose_checks) | {i for i, r in after.items() if r.get("required")})
    if not enforced:
        return PurposeResult((), ("purpose:no-tasks",))
    floors = {s["check"]: s["floor_score"] for s in policy.sacrifices}
    tasks, reasons = [], []
    for tid in enforced:
        a = after.get(tid)
        b = before.get(tid)
        status = a["status"] if a is not None else "missing"
        tasks.append({"task": tid, "status": status, "before": _score(b), "after": _score(a)})
        if _score(b) is None:
            before_status = b.get("status") if b is not None else "missing"
            if before_status not in ("error", "not_answerable", "missing"):
                before_status = "error"
            reasons.append(f"purpose:{tid}:before:{before_status}")
        if a is None or counts_as_fail(a):
            reasons.append(f"purpose:{tid}:{status}")
            continue
        score = a["score"]
        if not isinstance(score, float) or math.isnan(score) or math.isinf(score):
            reasons.append(f"purpose:{tid}:error")
        elif score < THRESHOLD and tid not in floors:
            reasons.append(f"purpose:{tid}:below-threshold")
        elif score < THRESHOLD and score < floors[tid]:
            reasons.append(f"purpose:{tid}:below-sacrifice-floor")
    return PurposeResult(tuple(tasks), tuple(sorted(reasons)))


def measured_utility(result: PurposeResult) -> dict:
    """The manifest's ``measured.utility`` block for an accepted result."""
    if not result.ok or not result.tasks:
        raise ValueError("purpose result not accepted")
    return {"status": "measured", "source": SOURCE,
            "tasks": [dict(t) for t in result.tasks if t["status"] in _TASK_STATUS]}


def scores(result: PurposeResult) -> dict:
    """{task: (before, after)} for the sacrifice rows."""
    return {t["task"]: (t["before"], t["after"]) for t in result.tasks}
