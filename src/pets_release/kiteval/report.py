"""Scorecard report gate. The kit exits 0 on errors and trusts empty denominators; this does not."""

from __future__ import annotations

import math
from collections.abc import Iterable
from numbers import Real

# Allowlist of exported top-level fields. Everything else stays in the scoring folder.
EXPORT_FIELDS = ("scenario", "dataset", "privacy", "utility", "composite", "tasks", "risks", "tables")


class ScorecardRejected(ValueError):
    """The report is not a clean, complete result. `reason` is a short content-free code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _num(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool) and not math.isnan(v)


def _scenario_id(report: dict):
    s = report.get("scenario")
    return s.get("id") if isinstance(s, dict) else None


def _check_tasks(report: dict, required_tasks: Iterable[str]) -> list[dict]:
    utility = report.get("utility")
    if not isinstance(utility, list):
        raise ScorecardRejected("structure")
    by_id = {}
    for u in utility:
        if not isinstance(u, dict) or "id" not in u:
            raise ScorecardRejected("structure")
        by_id[u["id"]] = u
    if any(u.get("metric") == "error" for u in utility):
        raise ScorecardRejected("error_status")
    for tid in required_tasks:
        if tid not in by_id:
            raise ScorecardRejected("missing_task")
    out = []
    required = set(required_tasks)
    for u in utility:
        is_required = bool(u.get("required")) or u["id"] in required
        scored = _num(u.get("score"))
        if is_required and not scored:
            raise ScorecardRejected("not_scored")
        out.append({"id": u["id"], "score": u["score"] if scored else None,
                    "required": is_required, "status": "ok" if scored else "not_answerable"})
    return out


def _check_table(name: str, tr: dict) -> None:
    status = tr.get("status")
    if status == "error" or "error" in tr:
        raise ScorecardRejected("error_status")
    if status not in ("released", "withheld"):
        raise ScorecardRejected("structure")
    if status == "withheld":
        return
    k = tr.get("k_anonymity")
    if isinstance(k, dict) and "n" in k and not (_num(k["n"]) and k["n"] > 0):
        raise ScorecardRejected("zero_denominator")
    for col in (tr.get("free_text") or {}).values():
        if not isinstance(col, dict) or col.get("status") == "withheld":
            continue
        if col.get("evaluated") and not (_num(col.get("n_values")) and col["n_values"] > 0):
            raise ScorecardRejected("zero_denominator")
    for res in (tr.get("linkage") or {}).values():
        if isinstance(res, dict) and res.get("evaluated") and "n_targets_in_data" in res:
            n = res["n_targets_in_data"]
            if n is not None and not (_num(n) and n > 0):
                raise ScorecardRejected("zero_denominator")


def validate_report(report: dict, *, scenario: str, required_tasks: Iterable[str],
                    tables: Iterable[str]) -> dict:
    """Return the allowlisted aggregate summary, or raise ScorecardRejected."""
    if not isinstance(report, dict):
        raise ScorecardRejected("structure")
    summary = report.get("summary")
    if not isinstance(summary, dict) or not all(_num(summary.get(k)) for k in ("privacy", "utility", "composite")):
        raise ScorecardRejected("structure")
    if _scenario_id(report) != scenario:
        raise ScorecardRejected("scenario")
    rep_tables = report.get("tables")
    if not isinstance(rep_tables, dict):
        raise ScorecardRejected("structure")
    for name in tables:
        if name not in rep_tables:
            raise ScorecardRejected("missing_table")
    for name, tr in rep_tables.items():
        if not isinstance(tr, dict):
            raise ScorecardRejected("structure")
        _check_table(name, tr)
    tasks = _check_tasks(report, list(required_tasks))
    risks = report.get("risk_components")
    if not isinstance(risks, dict) or not all(_num(v) for v in risks.values()):
        raise ScorecardRejected("structure")
    return {
        "scenario": scenario,
        "dataset": report.get("dataset"),
        "privacy": summary["privacy"],
        "utility": summary["utility"],
        "composite": summary["composite"],
        "tasks": tasks,
        "risks": {str(k): v for k, v in risks.items()},
        "tables": [{"table": n, "status": t["status"], "rows_original": t.get("rows_original"),
                    "rows_protected": t.get("rows_protected")} for n, t in rep_tables.items()],
    }
