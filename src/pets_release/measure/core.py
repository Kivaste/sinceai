"""Fill the manifest's `measured` block: scorecard before/after (via the kit-eval adapter only), our
person-k summary, and the published baselines. Aggregates only; nothing here prints or stores row values.

"Before" is the original data scored against itself (identity row maps), through the same adapter and
the same scenario, so before/after differ only in the release."""

from __future__ import annotations

import math
import re
import shutil
from numbers import Real
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from pets_release.kiteval import Lineage, run_scorecard
from pets_release.manifest import MANIFEST_SCHEMA, not_measured
from pets_release.measure.baselines import baseline_rows
from pets_release.measure.errors import MeasureRejected
from pets_release.measure.ids import K_BELOW_5_SHARE, K_BELOW_5_SUFFIX, RISK_AGGREGATES

_VALIDATOR = Draft202012Validator({"$defs": MANIFEST_SCHEMA["$defs"], **MANIFEST_SCHEMA["properties"]["measured"]})
_BAD_ID_CHARS = re.compile(r"[^A-Za-z0-9._:+-]")
_TASK_STATUS = ("ok", "not_answerable")
_SKIP_PREFIX = ("rowmap_", "_")


def measured_errors(block) -> list[str]:
    """Sorted content-free schema error paths for a `measured` block; `[]` means valid."""
    return sorted({"$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path)
                   + f": {e.validator}" for e in _VALIDATOR.iter_errors(block)})


def _finite(v) -> float:
    """A score or risk: a finite real in [0, 1]. Anything else is rejected, never clamped."""
    if isinstance(v, bool) or not isinstance(v, Real) or math.isnan(v) or math.isinf(v) or not 0.0 <= v <= 1.0:
        raise MeasureRejected("score")
    return float(v)


def _check_summary(summary, scenario: str) -> None:
    if not isinstance(summary, dict) or summary.get("scenario") != scenario:
        raise MeasureRejected("scenario")
    for key in ("privacy", "utility", "composite"):
        _finite(summary.get(key))
    for v in (summary.get("risks") or {}).values():
        _finite(v)


def _task_map(summary) -> dict:
    out = {}
    for t in summary.get("tasks") or []:
        if not isinstance(t, dict) or t.get("status") not in _TASK_STATUS:
            raise MeasureRejected("task_status")
        tid = t.get("id")
        if not isinstance(tid, str) or not tid or tid in out:
            raise MeasureRejected("task_status")
        score = t.get("score")
        if t["status"] == "ok":
            _finite(score)
        elif score is not None:
            raise MeasureRejected("task_status")
        out[tid] = t
    return out


def _utility(before: dict, after: dict) -> dict:
    b, a = _task_map(before), _task_map(after)
    if set(b) != set(a):
        raise MeasureRejected("task_mismatch")
    if not a:
        raise MeasureRejected("task_status")
    if any(t["status"] != "ok" for t in b.values()):
        raise MeasureRejected("before_not_answerable")  # the original data must answer every task
    tasks = [{"task": tid, "status": a[tid]["status"],
              "before": b[tid]["score"], "after": a[tid]["score"]} for tid in sorted(a)]
    return tasks


def _component_id(key: str, taken: set) -> str:
    base = ("risk." + _BAD_ID_CHARS.sub("_", key))[:60]
    cid, n = base, 1
    while cid in taken:
        n += 1
        cid = f"{base}_{n}"
    taken.add(cid)
    return cid


def _worst(risks: dict, suffix: str):
    vals = [_finite(v) for k, v in risks.items() if k.endswith(suffix)]
    return max(vals) if vals else None


def _row_count(v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        raise MeasureRejected("risk_rows")
    return v


def _weighted_k_share(summary: dict):
    """Row-weighted share of rows with k<5 over the tables scored for k: (share, sorted table names).

    Weighted tables are the released tables that report a k<5 rate; a released table with no rate is not
    scored for k and is excluded. Fails closed (risk_rows) if a rate has no released table entry or a
    weighted table's row count is missing, non-int, bool or <= 0. (None, []) when no table reports a rate."""
    rates = {k[: -len(K_BELOW_5_SUFFIX)]: _finite(v) for k, v in summary["risks"].items()
             if k.endswith(K_BELOW_5_SUFFIX)}
    tables = summary.get("tables")
    if not isinstance(tables, list):
        raise MeasureRejected("risk_rows")
    if not rates:
        return None, []  # the kit reports no k<5 rate for this scenario: not measured
    rows = {}
    for t in tables:
        if not isinstance(t, dict) or not isinstance(t.get("table"), str):
            raise MeasureRejected("risk_rows")
        if t.get("status") == "released" and t["table"] in rates:
            rows[t["table"]] = _row_count(t.get("rows_protected"))
    if set(rates) - set(rows):
        raise MeasureRejected("risk_rows")
    total = sum(rows.values())
    return sum(rates[t] * n for t, n in rows.items()) / total, sorted(rows)


def _privacy(before: dict, after: dict) -> tuple[list[dict], str]:
    """Privacy components only (utility and composite are not privacy), plus a note naming the tables the
    k<5 share was weighted over."""
    comps = [{"component": "privacy", "before": _finite(before["privacy"]), "after": _finite(after["privacy"])}]
    (share_b, tabs_b), (share_a, tabs_a) = _weighted_k_share(before), _weighted_k_share(after)
    note = ""
    if tabs_b or tabs_a:
        note = (f"; {K_BELOW_5_SHARE} row-weighted over the tables scored for k: "
                f"before={','.join(tabs_b)} after={','.join(tabs_a)}")
    if share_b is not None or share_a is not None:
        comps.append({"component": K_BELOW_5_SHARE, "before": share_b, "after": share_a})
    for cid, suffix in RISK_AGGREGATES.items():
        b, a = _worst(before["risks"], suffix), _worst(after["risks"], suffix)
        if b is not None or a is not None:
            comps.append({"component": cid, "before": b, "after": a})
    taken: set = set()
    keys = sorted(set(before["risks"]) | set(after["risks"]))
    for key in keys:
        comps.append({"component": _component_id(key, taken),
                      "before": _finite(before["risks"][key]) if key in before["risks"] else None,
                      "after": _finite(after["risks"][key]) if key in after["risks"] else None})
    return comps, note


def _identity_inputs(original_dir: Path, tables, record_keys: dict, out: Path):
    """Copy of the original tables as a stand-in release, identity row maps and lineage."""
    release, maps = out / "release", out / "rowmaps"
    release.mkdir(parents=True)
    maps.mkdir(parents=True)
    rowmaps, lineage = {}, {}
    for name in tables:
        shutil.copyfile(original_dir / f"{name}.csv", release / f"{name}.csv")
        key = record_keys.get(name)
        df = pd.read_csv(original_dir / f"{name}.csv", dtype=str, keep_default_na=False)
        if key not in df.columns:
            raise MeasureRejected("record_key")
        ids = list(df[key])
        pd.DataFrame({"protected_row": range(len(ids)), "original_record_id": ids}).to_csv(
            maps / f"rowmap_{name}.csv", index=False, lineterminator="\n")
        rowmaps[name] = maps / f"rowmap_{name}.csv"
        lineage[name] = Lineage(tuple(ids), frozenset())
    return release, rowmaps, lineage


def measure(scenario, *, root, original_dir, protected_dir, rowmaps: dict, lineage: dict, record_keys: dict,
            out_dir, person_k: list | None = None, search: dict | None = None,
            redaction: dict | None = None) -> dict:
    """The `measured` block for one release.

    Raises MeasureRejected (this module), or ScorecardRejected / RowMapRejected from the adapter: a wrong
    or missing scenario, an errored or incomplete scorecard, an unknown baseline all fail; nothing is
    zero-filled. `person_k` is `person_k_components(...)`; `search` and `redaction` are already-built
    `measured` sections (or None: not measured). Raw scorecards stay under `out_dir/{before,after}`."""
    if not isinstance(scenario, str) or not scenario.strip():
        raise MeasureRejected("scenario")
    original_dir, protected_dir, out_dir = Path(original_dir), Path(protected_dir), Path(out_dir)
    # "before" is the original's FULL table set: tables the release withholds keep their risk in "before"
    tables = sorted(f.stem for f in original_dir.glob("*.csv") if not f.stem.startswith(_SKIP_PREFIX))
    if not tables:
        raise MeasureRejected("original_tables")

    after = run_scorecard(original_dir, protected_dir, scenario=scenario, root=root, rowmaps=rowmaps,
                          lineage=lineage, out_dir=out_dir / "after")
    base = out_dir / "before"
    if base.exists():
        shutil.rmtree(base)
    release, id_maps, id_lineage = _identity_inputs(original_dir, tables, record_keys, base / "inputs")
    before = run_scorecard(original_dir, release, scenario=scenario, root=root, rowmaps=id_maps,
                           lineage=id_lineage, out_dir=base / "kit-out")
    for s in (before, after):
        _check_summary(s, scenario)

    privacy, k_note = _privacy(before, after)
    components = privacy + list(person_k or [])
    components.sort(key=lambda c: c["component"])
    if len({c["component"] for c in components}) != len(components):
        raise MeasureRejected("component_duplicate")
    source = f"pets-eval scorecard {scenario} via kiteval adapter; baselines: kit results/benchmark.json"
    block = {
        "utility": {"status": "measured", "source": source, "tasks": _utility(before, after)},
        "privacy": {"status": "measured", "source": source + k_note, "components": components},
        "search": search if search is not None else not_measured("search not run for this release"),
        "baselines": {"status": "measured", "source": "kit results/benchmark.json (published)",
                      "rows": baseline_rows(root, scenario, original_dir.name)},
        "redaction": redaction if redaction is not None else not_measured("redaction evaluation not run"),
    }
    errors = measured_errors(block)
    if errors:
        raise MeasureRejected("schema")
    return block
