"""Out-of-process scorecard: explicit scenario, explicit row maps, external output folder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pets_eval import attacks as kit_attacks
from pets_eval import io as kit_io
from pets_eval import scorecard as kit_scorecard

from pets_release.kiteval.report import ScorecardRejected, validate_report
from pets_release.kiteval.rowmap import Lineage, RowMapRejected, validate_row_map
from pets_release.offline import child_env
from pets_release.offline import install as install_offline_guard


def _read_str(path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, **kw)


def _load_catalog(root: Path) -> pd.DataFrame:
    """The field catalog as strings (same shape as pets_eval.io.load_catalog, without type or NA parsing)."""
    df = _read_str(Path(root) / "metadata" / "field_catalog.csv")
    if "art9_special_category" in df:
        df["art9_special_category"] = df.art9_special_category.str.lower().isin(["true", "1", "yes"])
    return df


def _load_identity_truth(root: Path, dataset: str, table: str):
    """pets-eval locates the identity file, not us; only 'any person id present' is used here."""
    return kit_io.load_identity_truth(root, dataset, table)


def _tables(folder: Path) -> dict[str, Path]:
    return {f.stem: f for f in sorted(folder.glob("*.csv"))
            if not f.stem.startswith(("rowmap_", "_"))}


def _inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child == parent or parent in child.parents


MANIFEST = "privacy_manifest.json"


def _scan_release(protected_dir: Path, orig_files: dict) -> None:
    """The release folder holds exactly the protected table files (named like original tables) and
    the manifest. Anything else, including files the evaluator would silently ignore (`_x.csv`), is
    refused: the scan and the scoring share this one allowlist."""
    allowed = {f"{name}.csv" for name in orig_files} | {MANIFEST}
    for entry in sorted(protected_dir.iterdir()):
        if entry.name.startswith("rowmap_"):
            raise RowMapRejected("rowmap_in_release")
        if entry.is_dir() or entry.name not in allowed:
            raise ScorecardRejected("release_extra_file")

def _expected_sections(root: Path, dataset: str, scen: dict, catalog, tables: dict,
                       release: dict) -> dict:
    """Result sections the kit should produce for each table, from the kit's own metadata:
    free-text leakage for catalogued free-text columns with gold spans; the linkage attacks its
    spec/adversary selection runs when the kit ships identity data for the table; trajectory unicity per spec; and
    the release's columns, used to prove an input was really removed."""
    all_specs = kit_io.load_attack_specs(root)
    spec_file = root / "metadata" / "attack_specs.json"
    trajectories = json.loads(spec_file.read_text(encoding="utf-8")).get("trajectories", []) if spec_file.exists() else []
    out = {}
    for name, path in tables.items():
        cols = set(_read_str(path, nrows=0).columns)
        text = catalog[(catalog.table == name) & (catalog.privacy_role == "free_text")].column
        specs = [s for s in all_specs if s["dataset"] == dataset and s["table"] == name]
        linkage = None
        identity = _load_identity_truth(root, dataset, name)
        if identity is not None and identity.iloc[:, 1].astype(str).str.len().gt(0).any():  # as the kit does
            adversaries = kit_scorecard._adversaries_for(root, dataset, scen)
            if not specs and any(s["dataset"] == dataset for s in all_specs):
                attacks = []
            elif specs:
                chosen = [s for s in specs if s["adversary"] in adversaries] or specs
                attacks = sorted({s["adversary"] for s in chosen})
            else:
                attacks = sorted(adversaries)
            # adversaries whose every selected spec needs only columns this release no longer has
            # (the kit's own qis_from_spec decides); only these may report "no targets, no QIs used"
            no_cols = sorted(a for a in attacks if all(
                not kit_attacks.qis_from_spec(s["qis"], release.get(name, ())) for s in specs if s["adversary"] == a)
                and any(s["adversary"] == a for s in specs))
            linkage = {"attacks": attacks, "no_attack_columns": no_cols}
        out[name] = {
            "free_text": sorted(c for c in text if c in cols and kit_io.spans_path(root, dataset, name, c).exists()),
            "linkage": linkage,
            "trajectories": {t["user"]: {"time": t["time"],
                                         "location": [t[k] for k in ("lat", "lon", "place") if t.get(k)]}
                             for t in trajectories if t["dataset"] == dataset and t["table"] == name},
            "columns": sorted(release.get(name, ())),
        }
    return out

def run_scorecard(original_dir, protected_dir, *, scenario: str, root, rowmaps: dict[str, str | Path],
                  lineage: dict[str, Lineage], out_dir) -> dict:
    """Validate row maps, run pets-eval scorecard in a child process, validate the report,
    and return the allowlisted aggregate summary. Raw output stays in `out_dir`.

    lineage (table -> the writer's Lineage) is required for every protected table: without it a row map
    can only be checked structurally, not for swapped or wrongly suppressed records.
    All paths are resolved to absolute before the child starts (its cwd is out_dir).

    Raises ScorecardRejected / RowMapRejected; nothing missing, errored or empty passes.

    Offline: installs the guard in this process and launches the evaluator with `child_env`, whatever
    route the caller came in by."""
    install_offline_guard()
    original_dir, protected_dir, root, out_dir = (Path(p).resolve() for p in (original_dir, protected_dir, root, out_dir))
    rowmaps = {t: Path(p).resolve() for t, p in rowmaps.items()}
    if _inside(out_dir, protected_dir) or _inside(protected_dir, out_dir):
        raise ScorecardRejected("out_dir_inside_release")
    if any(_inside(p, protected_dir) for p in rowmaps.values()):
        raise RowMapRejected("rowmap_in_release")  # row maps are private scoring aids
    scen = kit_io.get_scenario(scenario, root)
    if not scen or scen.get("dataset") != original_dir.name:
        raise ScorecardRejected("scenario")

    orig_files = _tables(original_dir)
    _scan_release(protected_dir, orig_files)
    prot_files = _tables(protected_dir)
    catalog = _load_catalog(root)
    catalog = catalog[catalog.dataset == original_dir.name]
    orig_rows = {name: len(pd.read_csv(f, dtype=str, keep_default_na=False)) for name, f in orig_files.items()}
    prot_rows_by_table: dict[str, int] = {}
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
        prot_rows_by_table[name] = prot_rows
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
    env = child_env({**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"})
    proc = subprocess.run(cmd, env=env, capture_output=True, check=False, cwd=str(out_dir))
    (out_dir / "evaluator.log").write_bytes(proc.stdout + b"\n--- stderr ---\n" + proc.stderr)
    if proc.returncode != 0:
        raise ScorecardRejected("evaluator_failed")
    try:
        report = json.loads((out_dir / "scorecard.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ScorecardRejected("structure") from None
    return validate_report(report, scenario=scenario, required_tasks=scen.get("utility_requirements", []),
                           tables=orig_rows, released=prot_rows_by_table, expected_sections=_expected_sections(
                               root, original_dir.name, scen, catalog, orig_files,
                               {n: _read_str(p, nrows=0).columns for n, p in prot_files.items()}))







