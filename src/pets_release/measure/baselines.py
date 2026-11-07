"""Baselines B0 / B2 / B2-k, read from the kit's published `results/benchmark.json` (aggregates only)."""

from __future__ import annotations

import json
import math
import re
from numbers import Real
from pathlib import Path

from pets_release.measure.errors import MeasureRejected

BASELINES = (("B0", "B0"), ("B2", "B2"), ("B2-k", "B2K"))  # (manifest id, key prefix in benchmark.json)
HEADLINE = ("privacy", "utility", "composite", "worst_reid", "residual_identifiers")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}")


def _value(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, Real) or math.isnan(v) or math.isinf(v):
        raise MeasureRejected("baseline_structure")
    return float(v)


def _load(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise MeasureRejected("baseline_missing") from None
    except ValueError:
        raise MeasureRejected(what) from None


def baseline_rows(root, scenario: str, dataset: str) -> list[dict]:
    """Rows `{baseline, metric, value}` for the scenario, sorted by (baseline, metric).

    Fails (MeasureRejected) if the scenario or a baseline is not in the published files; a published null
    stays null."""
    root = Path(root)
    scenarios = _load(root / "metadata" / "scenarios.json", "baseline_structure")
    match = [s for s in scenarios if isinstance(s, dict) and s.get("id") == scenario] if isinstance(
        scenarios, list) else []
    if len(match) != 1 or match[0].get("dataset") != dataset:
        raise MeasureRejected("baseline_scenario")
    required = list(match[0].get("utility_requirements") or [])
    bench = _load(root / "results" / "benchmark.json", "baseline_structure")
    published = bench.get("baselines") if isinstance(bench, dict) else None
    if not isinstance(published, dict):
        raise MeasureRejected("baseline_structure")
    rows = []
    for baseline, prefix in BASELINES:
        rec = published.get(f"{prefix}_{dataset}")
        if not isinstance(rec, dict):
            raise MeasureRejected("baseline_missing")
        by_scenario = rec.get("utility_by_scenario")
        tasks = rec.get("utility_tasks")
        if not isinstance(by_scenario, dict) or not isinstance(tasks, dict):
            raise MeasureRejected("baseline_structure")
        if scenario not in by_scenario:
            raise MeasureRejected("baseline_scenario")
        for metric in HEADLINE:
            if metric not in rec:
                raise MeasureRejected("baseline_structure")
            rows.append({"baseline": baseline, "metric": metric, "value": _value(rec[metric])})
        rows.append({"baseline": baseline, "metric": f"utility.{scenario}", "value": _value(by_scenario[scenario])})
        for task in required:
            if task not in tasks:
                raise MeasureRejected("baseline_structure")
            rows.append({"baseline": baseline, "metric": f"task.{task}", "value": _value(tasks[task])})
    if not all(_ID.fullmatch(r["metric"]) for r in rows):
        raise MeasureRejected("baseline_structure")
    return sorted(rows, key=lambda r: (r["baseline"], r["metric"]))
