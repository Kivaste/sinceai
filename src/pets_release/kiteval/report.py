"""Scorecard report gate. The kit exits 0 on errors and trusts empty denominators; this does not.

Fail closed: a record that is absent, incomplete, errored or unavailable is a rejection."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from numbers import Integral, Real

# Allowlist of exported top-level fields. Everything else stays in the scoring folder.
EXPORT_FIELDS = ("scenario", "dataset", "privacy", "utility", "composite", "tasks", "risks", "tables")

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # scenario, dataset, task and table names
_RISK_KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ :<>=()./+-]{0,119}")
_TASK_STATUS = ("ok", "not_answerable")


class ScorecardRejected(ValueError):
    """The report is not a clean, complete result. `reason` is a short content-free code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _num(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool) and not math.isnan(v) and not math.isinf(v)


def _int(v) -> bool:
    return isinstance(v, Integral) and not isinstance(v, bool)


def _name(v) -> bool:
    return isinstance(v, str) and _ID.fullmatch(v) is not None


def _scenario_id(report: dict):
    s = report.get("scenario")
    return s.get("id") if isinstance(s, dict) else None


def _walk(node):
    """Yield every dict nested anywhere in the node."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _scan_nested(table: dict) -> None:
    """Errored or unavailable sub-results anywhere in a table record are a fail."""
    for d in _walk(table):
        if "error" in d or "trace" in d:
            raise ScorecardRejected("error_status")
        if d.get("evaluated") is False:
            reason = str(d.get("reason", "")).lower()
            if reason.startswith("error"):
                raise ScorecardRejected("error_status")
            if "row map" in reason:
                raise ScorecardRejected("not_evaluated")
        note = d.get("note")
        if isinstance(note, str) and note.lower().startswith("no row map"):
            raise ScorecardRejected("not_evaluated")


def _check_tasks(report: dict, required_tasks: list[str]) -> list[dict]:
    utility = report.get("utility")
    if not isinstance(utility, list):
        raise ScorecardRejected("structure")
    by_id = {}
    for u in utility:
        if not isinstance(u, dict) or not _name(u.get("id")):
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
        is_required = u.get("required") is True or u["id"] in required
        scored = _num(u.get("score")) and 0.0 <= u["score"] <= 1.0
        if is_required and not scored:
            raise ScorecardRejected("not_scored")
        out.append({"id": u["id"], "score": float(u["score"]) if scored else None,
                    "required": is_required, "status": "ok" if scored else "not_answerable"})
    return out


def _positive(v) -> bool:
    return _num(v) and v > 0


def _check_released(tr: dict) -> None:
    if not _int(tr.get("rows_original")) or not _int(tr.get("rows_protected")):
        raise ScorecardRejected("structure")
    if tr["rows_original"] <= 0 or tr["rows_protected"] <= 0:
        raise ScorecardRejected("zero_denominator")
    risks = tr.get("risks")
    if not isinstance(risks, dict) or not all(_num(v) for v in risks.values()):
        raise ScorecardRejected("structure")
    k = tr.get("k_anonymity")
    if not isinstance(k, dict):
        raise ScorecardRejected("structure")
    if "n" in k:
        if not _positive(k["n"]):
            raise ScorecardRejected("zero_denominator")
    elif not isinstance(k.get("note"), str):
        raise ScorecardRejected("structure")
    for col in (tr.get("free_text") or {}).values():
        if not isinstance(col, dict) or "evaluated" not in col:
            raise ScorecardRejected("structure")
        if col["evaluated"] is True and col.get("status") != "withheld" and not _positive(col.get("n_values")):
            raise ScorecardRejected("zero_denominator")
    for res in (tr.get("linkage") or {}).values():
        if not isinstance(res, dict) or "evaluated" not in res:
            continue  # table-level note; nested notes are scanned separately
        if res["evaluated"] is True:
            if "n_targets_in_data" not in res:
                raise ScorecardRejected("structure")
            n = res["n_targets_in_data"]
            if n is None:
                if res.get("qis_used") != []:
                    raise ScorecardRejected("structure")
            elif not _positive(n):
                raise ScorecardRejected("zero_denominator")


def _check_table(name: str, tr: dict) -> dict:
    if not _name(name):
        raise ScorecardRejected("structure")
    _scan_nested(tr)
    status = tr.get("status")
    if status == "error":
        raise ScorecardRejected("error_status")
    if status not in ("released", "withheld"):
        raise ScorecardRejected("structure")
    if not _int(tr.get("rows_original")) and status == "withheld":
        raise ScorecardRejected("structure")
    if status == "released":
        _check_released(tr)
    return {"table": name, "status": status, "rows_original": int(tr["rows_original"]),
            "rows_protected": int(tr["rows_protected"]) if status == "released" else None}


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
    if not _name(report.get("dataset")) or not _name(scenario):
        raise ScorecardRejected("structure")
    rep_tables = report.get("tables")
    if not isinstance(rep_tables, dict):
        raise ScorecardRejected("structure")
    for name in tables:
        if name not in rep_tables:
            raise ScorecardRejected("missing_table")
    exported_tables = []
    for name, tr in rep_tables.items():
        if not isinstance(tr, dict):
            raise ScorecardRejected("structure")
        exported_tables.append(_check_table(name, tr))
    tasks = _check_tasks(report, list(required_tasks))
    risks = report.get("risk_components")
    if not isinstance(risks, dict) or not all(
            isinstance(k, str) and _RISK_KEY.fullmatch(k) and _num(v) for k, v in risks.items()):
        raise ScorecardRejected("structure")
    return {
        "scenario": scenario,
        "dataset": report["dataset"],
        "privacy": float(summary["privacy"]),
        "utility": float(summary["utility"]),
        "composite": float(summary["composite"]),
        "tasks": tasks,
        "risks": {k: float(v) for k, v in risks.items()},
        "tables": exported_tables,
    }
