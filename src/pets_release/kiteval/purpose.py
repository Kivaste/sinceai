"""Purpose checks: the scenario's utility tasks, run in-process on typed disposable copies."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from pets_eval import io as kit_io
from pets_eval.utility import all_tasks

from pets_release.kiteval.report import ScorecardRejected


def _typed(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Disposable copy typed exactly as the kit types a CSV it reads: written out, read back with
    the kit's own reader. The caller's string tables are never modified."""
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, df in tables.items():
            path = Path(tmp) / f"{name}.csv"
            df.to_csv(path, index=False)
            out[name] = kit_io.read_table(path)
    return out


def _run(task, original_typed, protected_typed, required: bool) -> dict:
    try:
        res = task.fn(original_typed, protected_typed)
    except Exception:  # noqa: BLE001 - message could carry values; keep only the code
        return {"id": task.id, "score": None, "status": "error", "required": required}
    score = res.get("score")
    if score is None:
        return {"id": task.id, "score": None, "status": "not_answerable", "required": required}
    return {"id": task.id, "score": float(score), "status": "ok", "required": required}


def _scenario(scenario_id: str, root) -> dict:
    scen = kit_io.get_scenario(scenario_id, root)
    if not scen:
        raise ScorecardRejected("scenario")
    return scen


def purpose_checks(scenario_id: str, original: dict[str, pd.DataFrame],
                   protected: dict[str, pd.DataFrame], *, root) -> list[dict]:
    """One result per scenario task: {id, score, status, required}. A required task the kit does
    not have comes back with status 'missing'."""
    scen = _scenario(scenario_id, root)
    required = list(scen.get("utility_requirements", []))
    tasks = [t for t in all_tasks([scen["dataset"]])
             if t.dataset == scen["dataset"] and (t.id in required or scenario_id in (t.scenarios or []))]
    known = {t.id for t in tasks}
    orig_t, prot_t = _typed(original), _typed(protected)
    results = [_run(t, orig_t, prot_t, t.id in required or not required) for t in tasks]
    results += [{"id": r, "score": None, "status": "missing", "required": True} for r in required if r not in known]
    return sorted(results, key=lambda r: r["id"])


def purpose_check(task_id: str, original: dict[str, pd.DataFrame],
                  protected: dict[str, pd.DataFrame]) -> dict:
    """Run one named utility task."""
    matches = [t for t in all_tasks() if t.id == task_id]
    if not matches:
        return {"id": task_id, "score": None, "status": "missing", "required": True}
    return _run(matches[0], _typed(original), _typed(protected), True)


def counts_as_fail(result: dict) -> bool:
    """Only a scored, error-free task passes. Error, not answerable, missing: all fail."""
    return not (result.get("status") == "ok" and result.get("score") is not None)
