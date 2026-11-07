"""Out-of-process scorecard: explicit scenario, explicit row maps, external output folder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pets_eval import io as kit_io

from pets_release.kiteval.report import ScorecardRejected, validate_report
from pets_release.kiteval.rowmap import Lineage, RowMapRejected, validate_row_map


def _tables(folder: Path) -> dict[str, Path]:
    return {f.stem: f for f in sorted(folder.glob("*.csv"))
            if not f.stem.startswith(("rowmap_", "_"))}


def _inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child == parent or parent in child.parents


def run_scorecard(original_dir, protected_dir, *, scenario: str, root, rowmaps: dict[str, str | Path],
                  lineage: dict[str, Lineage], out_dir) -> dict:
    """Validate row maps, run pets-eval scorecard in a child process, validate the report,
    and return the allowlisted aggregate summary. Raw output stays in `out_dir`.

    lineage (table -> the writer's Lineage) is required for every protected table: without it a row map
    can only be checked structurally, not for swapped or wrongly suppressed records.
    All paths are resolved to absolute before the child starts (its cwd is out_dir).

    Raises ScorecardRejected / RowMapRejected; nothing missing, errored or empty passes."""
    original_dir, protected_dir, root, out_dir = (Path(p).resolve() for p in (original_dir, protected_dir, root, out_dir))
    rowmaps = {t: Path(p).resolve() for t, p in rowmaps.items()}
    if _inside(out_dir, protected_dir) or _inside(protected_dir, out_dir):
        raise ScorecardRejected("out_dir_inside_release")
    scen = kit_io.get_scenario(scenario, root)
    if not scen or scen.get("dataset") != original_dir.name:
        raise ScorecardRejected("scenario")

    orig_files, prot_files = _tables(original_dir), _tables(protected_dir)
    catalog = kit_io.load_catalog(root)
    catalog = catalog[catalog.dataset == original_dir.name]
    for name, pfile in prot_files.items():
        if name not in orig_files:
            raise ScorecardRejected("unknown_table")
        if name not in rowmaps:
            raise RowMapRejected("missing_map")
        if name not in lineage:
            raise RowMapRejected("missing_lineage")
        orig = pd.read_csv(orig_files[name], dtype=str, keep_default_na=False)
        key = kit_io.record_key(catalog, original_dir.name, name, orig)
        if key is None:
            raise RowMapRejected("no_source_key")
        prot_rows = len(pd.read_csv(pfile, dtype=str, keep_default_na=False))
        validate_row_map(rowmaps[name], protected_rows=prot_rows, source_keys=orig[key], expected_lineage=lineage[name])
    if set(rowmaps) - set(prot_files):
        raise RowMapRejected("map_without_table")

    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / "scorecard.json"
    if stale.exists():
        stale.unlink()  # a leftover report must never stand in for this run
    cmd = [sys.executable, "-m", "pets_eval", "scorecard", "--original", str(original_dir),
           "--protected", str(protected_dir), "--scenario", scenario, "--root", str(root),
           "--out", str(out_dir)]
    for table in sorted(rowmaps):
        cmd += ["--rowmap", f"{table}={rowmaps[table]}"]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"}
    proc = subprocess.run(cmd, env=env, capture_output=True, check=False, cwd=str(out_dir))
    (out_dir / "evaluator.log").write_bytes(proc.stdout + b"\n--- stderr ---\n" + proc.stderr)
    if proc.returncode != 0:
        raise ScorecardRejected("evaluator_failed")
    try:
        report = json.loads((out_dir / "scorecard.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ScorecardRejected("structure") from None
    return validate_report(report, scenario=scenario,
                           required_tasks=scen.get("utility_requirements", []), tables=orig_files)


