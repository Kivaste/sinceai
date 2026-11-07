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

_VALIDATOR = Draft202012Validator({"$defs": MANIFEST_SCHEMA["$defs"], **MANIFEST_SCHEMA["properties"]["measured"]})
_BAD_ID_CHARS = re.compile(r"[^A-Za-z0-9._:+-]")
_TASK_STATUS = ("ok", "not_answerable")
_SKIP_PREFIX = ("rowmap_", "_")


def measured_errors(block) -> list[str]:
    """Sorted content-free schema error paths for a `measured` block; `[]` means valid."""
    return sorted({"$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path)
                   + f": {e.validator}" for e in _VALIDATOR.iter_errors(block)})


def _finite(v) -> float:
    if isinstance(v, bool) or not isinstance(v, Real) or math.isnan(v) or math.isinf(v):
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
        if not isinstance(t, dict) or t.get("status") not in _TASK_STATUS or t["id"] in out:
            raise MeasureRejected("task_status")
        score = t.get("score")
        if t["status"] == "ok":
            _finite(score)
        elif score is not None:
            raise MeasureRejected("task_status")
        out[t["id"]] = t
    return out


def _utility(before: dict, after: dict) -> dict:
    b, a = _task_map(before), _task_map(after)
    if set(b) != set(a):
        raise MeasureRejected("task_mismatch")
    if not a:
        raise MeasureRejected("task_status")
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


def _privacy(before: dict, after: dict) -> list[dict]:
    comps = [{"component": f"summary.{k}", "before": _finite(before[k]), "after": _finite(after[k])}
             for k in ("composite", "privacy", "utility")]
    taken: set = set()
    keys = sorted(set(before["risks"]) | set(after["risks"]))
    for key in keys:
        comps.append({"component": _component_id(key, taken),
                      "before": _finite(before["risks"][key]) if key in before["risks"] else None,
                      "after": _finite(after["risks"][key]) if key in after["risks"] else None})
    return comps


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
            maps / f"rowmap_{name}.csv", index=False)
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
    tables = sorted(f.stem for f in protected_dir.glob("*.csv") if not f.stem.startswith(_SKIP_PREFIX))

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

    components = _privacy(before, after) + list(person_k or [])
    components.sort(key=lambda c: c["component"])
    if len({c["component"] for c in components}) != len(components):
        raise MeasureRejected("component_duplicate")
    source = f"pets-eval scorecard {scenario} via kiteval adapter; baselines: kit results/benchmark.json"
    block = {
        "utility": {"status": "measured", "source": source, "tasks": _utility(before, after)},
        "privacy": {"status": "measured", "source": source, "components": components},
        "search": search if search is not None else not_measured("search not run for this release"),
        "baselines": {"status": "measured", "source": "kit results/benchmark.json (published)",
                      "rows": baseline_rows(root, scenario, original_dir.name)},
        "redaction": redaction if redaction is not None else not_measured("redaction evaluation not run"),
    }
    errors = measured_errors(block)
    if errors:
        raise MeasureRejected("schema")
    return block
