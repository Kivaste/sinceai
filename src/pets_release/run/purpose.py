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
SOURCE_LINEAGE = (SOURCE + "; pseudonymised record keys the checks match on restored through the producer row map; "
                  "<task>.unmodified = score without it (not gated)")
_TASK_STATUS = ("ok", "error", "not_answerable")  # manifest measured.utility statuses


@dataclass(frozen=True)
class PurposeResult:
    tasks: tuple  # ({"task", "status", "before", "after"}, ...) sorted by task; status may be "missing"
    reasons: tuple  # content-free reason codes; empty means accepted
    lineage: bool = False  # scored through the producer row map (purpose_lineage)

    @property
    def ok(self) -> bool:
        return not self.reasons


def _by_id(results) -> dict:
    return {r["id"]: r for r in results}


def _score(r):
    return r["score"] if r is not None and r.get("status") == "ok" else None


def _lineage(policy, released, rowmaps):
    """``released`` with the scenario's purpose-lineage record keys restored through the producer row maps.

    Only tables with a producer row map are restored: the producer context builds one exactly when the record key
    is released as a pseudonym (token inversion, never a file). None when nothing was restored. Raises
    LineageError when a row map does not cover its table."""
    from pets_release.cs_s1.lineage import restore_record_keys
    from pets_release.run.context import SCENARIO_SPEC

    lineage = SCENARIO_SPEC.get(policy.scenario, {}).get("purpose_lineage", {})
    hit = sorted(t for t in lineage if rowmaps and t in rowmaps and t in released)
    if not hit:
        return None
    out = dict(released)
    for t in hit:
        out[t] = restore_record_keys(released[t], rowmaps[t], lineage[t])
    return out


def evaluate(policy, source, released, *, root, rowmaps=None) -> PurposeResult:
    """Evaluate ``released`` ({table: DataFrame}) against ``source`` for ``policy``'s scenario. Never raises.

    ``rowmaps``: the producer row maps (``run.context``). For a scenario with ``purpose_lineage`` record keys
    released as pseudonyms, the gated scores are on the release with those keys restored through the row map;
    each enforced task whose score differs without it is added as an ungated ``<task>.unmodified`` entry.
    """
    from pets_release.cs_s1.lineage import LineageError
    from pets_release.kiteval import counts_as_fail, purpose_checks

    try:
        restored = _lineage(policy, released, rowmaps)
    except LineageError:
        return PurposeResult((), ("purpose:lineage:error",))
    try:
        after = _by_id(purpose_checks(policy.scenario, source, restored or released, root=root))
        before = _by_id(purpose_checks(policy.scenario, source, source, root=root))
        raw = _by_id(purpose_checks(policy.scenario, source, released, root=root)) if restored else {}
    except Exception:  # noqa: BLE001 - adapter text could carry values; keep the code only
        return PurposeResult((), ("purpose:unavailable",))
    enforced = sorted(set(policy.purpose_checks) | {i for i, r in after.items() if r.get("required")})
    floors = {s["check"]: s["floor_score"] for s in policy.sacrifices}
    tasks, reasons = [], []
    for tid in enforced:
        a = after.get(tid)
        status = a["status"] if a is not None else "missing"
        tasks.append({"task": tid, "status": status, "before": _score(before.get(tid)), "after": _score(a)})
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
    for tid in enforced:  # disclosure only: never gated
        r, a = raw.get(tid), after.get(tid)
        if r is not None and a is not None and (r.get("status"), _score(r)) != (a.get("status"), _score(a)):
            st = r["status"] if r.get("status") in _TASK_STATUS else "error"
            tasks.append({"task": f"{tid}.unmodified", "status": st, "before": _score(before.get(tid)),
                          "after": _score(r)})
    tasks.sort(key=lambda t: t["task"])
    return PurposeResult(tuple(tasks), tuple(sorted(reasons)), lineage=restored is not None)


def measured_utility(result: PurposeResult) -> dict:
    """The manifest's ``measured.utility`` block for an accepted result."""
    if not result.ok or not result.tasks:
        raise ValueError("purpose result not accepted")
    return {"status": "measured", "source": SOURCE_LINEAGE if result.lineage else SOURCE,
            "tasks": [dict(t) for t in result.tasks if t["status"] in _TASK_STATUS]}


def scores(result: PurposeResult) -> dict:
    """{task: (before, after)} for the sacrifice rows."""
    return {t["task"]: (t["before"], t["after"]) for t in result.tasks}
