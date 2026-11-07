"""Purpose checks: the scenario's utility tasks, run in-process on typed disposable copies."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pets_eval import io as kit_io
from pets_eval.utility import all_tasks

from pets_release.kiteval.numeric_columns import NUMERIC_COLUMNS
from pets_release.kiteval.report import ScorecardRejected


def _prepared(tables: dict[str, pd.DataFrame], measures: frozenset) -> dict[str, pd.DataFrame]:
    """Disposable copy for one task. Everything stays a string (blank = missing, as the kit reads it)
    except the task's numeric measure columns (NUMERIC_COLUMNS), which become numbers when every
    non-blank value parses as one. Categories and text are never converted."""
    out = {}
    for name, df in tables.items():
        cp = df.copy()
        for col in cp.columns:
            cp[col] = cp[col].where(cp[col] != "", np.nan)
            if (name, col) in measures:
                num = pd.to_numeric(cp[col], errors="coerce")
                if num.isna().equals(cp[col].isna()):
                    cp[col] = num
        out[name] = cp
    return out


def _run(task, original, protected, required: bool) -> dict:
    try:
        measures = NUMERIC_COLUMNS[task.id]  # no entry: refuse to guess types
        res = task.fn(_prepared(original, measures), _prepared(protected, measures))
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
    results = [_run(t, original, protected, t.id in required or not required) for t in tasks]
    results += [{"id": r, "score": None, "status": "missing", "required": True} for r in required if r not in known]
    return sorted(results, key=lambda r: r["id"])


def purpose_check(task_id: str, original: dict[str, pd.DataFrame],
                  protected: dict[str, pd.DataFrame]) -> dict:
    """Run one named utility task."""
    matches = [t for t in all_tasks() if t.id == task_id]
    if not matches:
        return {"id": task_id, "score": None, "status": "missing", "required": True}
    return _run(matches[0], original, protected, True)


def counts_as_fail(result: dict) -> bool:
    """Only a scored, error-free task passes. Error, not answerable, missing: all fail."""
    return not (result.get("status") == "ok" and result.get("score") is not None)


