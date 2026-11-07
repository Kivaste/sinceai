"""Release writer: build in a hidden temp folder, gate, assemble + sign, self-scan, then rename atomically."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pets_release.checks import RegistryError, all_checks, run_checks
from pets_release.kit import Kit, KitError
from pets_release.kiteval import Lineage
from pets_release.manifest import (
    MANIFEST_FILENAME,
    SCENARIOS,
    canonical_bytes,
    validate_manifest,
    validate_manifest_file,
)
from pets_release.policy import contract_policy_problems
from pets_release.pseudonym import manifest_signing_key
from pets_release.writer.assemble import (
    NARRATIVE_KEYS,
    assemble_manifest,
    evidence_for,
    justification_reasons,
)

FILE_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}\.csv$")
SCORING_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,99}$")
SCAN_MIN_LEN = 6  # released cell values at least this long must not appear in manifest text (outside `contract`)
REFUSAL_REPORT = "refusal_report.json"
GATE_REPORT = "gate_report.json"
LINEAGE_FILE = "lineage.json"


class WriterError(Exception):
    """Invalid call (bad candidate, existing output, narrowed check selection). Nothing was written. No values."""


@dataclass(frozen=True)
class ProtectedTable:
    name: str                 # release file name, e.g. "ed_visits.csv"
    frame: pd.DataFrame       # every cell a str; column names = header
    final: Sequence[str]      # source record key of each row of ``frame`` (same order)
    suppressed: frozenset     # source record keys dropped from this table


@dataclass(frozen=True)
class Candidate:
    scenario: str
    recipient: str
    tables: tuple
    contract: dict
    tool_revision: str                 # 40-hex git revision
    created: str                       # "YYYY-MM-DDTHH:MM:SSZ" (passed in; never wall clock)
    narrative: Mapping[str, object]    # exactly NARRATIVE_KEYS
    lexicon_digests: Mapping[str, str] = field(default_factory=dict)
    scoring_files: Mapping[str, bytes] = field(default_factory=dict)  # e.g. search log; scoring folder only


@dataclass(frozen=True)
class WriteResult:
    status: str        # "released" | "refused"
    out: Path          # the release folder (exists only when released)
    scoring: Path      # <out>.scoring
    reasons: tuple     # content-free codes; empty when released


def scoring_dir(out) -> Path:
    out = Path(out)
    return out.with_name(out.name + ".scoring")


def _validate(c: Candidate) -> None:
    if c.scenario not in SCENARIOS:
        raise WriterError("unknown scenario")
    if set(c.narrative) != set(NARRATIVE_KEYS):
        raise WriterError("narrative keys must be exactly NARRATIVE_KEYS")
    names = [t.name for t in c.tables]
    if not names or len(set(names)) != len(names) or not all(isinstance(n, str) and FILE_NAME.match(n) for n in names):
        raise WriterError("table names must be unique release file names")
    for t in c.tables:
        cols = list(t.frame.columns)
        if not all(isinstance(x, str) for x in cols) or len(set(cols)) != len(cols):
            raise WriterError("columns must be unique strings")
        if not all(type(v) is str for v in t.frame.to_numpy(dtype=object).ravel()):
            raise WriterError("every cell must be a str")
        final = list(t.final)
        if len(final) != len(t.frame) or not all(type(k) is str for k in final) or len(set(final)) != len(final):
            raise WriterError("lineage must give one unique source key per row")
        if not all(type(k) is str for k in t.suppressed) or set(final) & set(t.suppressed):
            raise WriterError("suppressed keys must be str and disjoint from final keys")
    for name in c.scoring_files:
        if not SCORING_NAME.match(name) or name in (REFUSAL_REPORT, GATE_REPORT, LINEAGE_FILE) \
                or name.lower().startswith("rowmap_"):
            raise WriterError("bad scoring file name")


def _input_digests(kit: Kit, scenario: str) -> dict:
    """SHA-256 of every table of the scenario's dataset (withheld tables included), via ticket 01's kit access."""
    if not isinstance(kit, Kit):
        raise WriterError("kit must be a pets_release.kit.Kit")
    try:
        dataset = kit.scenario(scenario).get("dataset")
        digests = kit.input_digests(dataset)
    except (KitError, OSError) as e:
        raise WriterError("kit inputs unavailable for scenario") from e
    if not digests:
        raise WriterError("scenario dataset has no tables")
    return dict(sorted(digests.items()))


def _registry_reasons(records) -> list[str]:
    """The gate's records must be exactly the registry's checks (name, version, scope, unit), in order."""
    try:
        reg = [(c.name, c.version, c.scope, c.unit) for c in all_checks()]
    except RegistryError:
        return ["gate:registry-error"]
    got = [(r.check, r.version, r.scope, r.denominator.get("unit")) for r in records]
    return [] if got == reg else ["gate:registry-mismatch"]


def _csv_bytes(header, rows) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _write_tables(build: Path, c: Candidate) -> tuple[dict, dict]:
    """Write sorted tables. Returns (file digests, {stem: Lineage}) with lineage in written row order."""
    digests, lineage = {}, {}
    for t in sorted(c.tables, key=lambda t: t.name):
        pairs = sorted(zip(t.frame.itertuples(index=False, name=None), t.final, strict=True))
        data = _csv_bytes(list(t.frame.columns), [list(r) for r, _ in pairs])
        (build / t.name).write_bytes(data)
        digests[t.name] = hashlib.sha256(data).hexdigest()
        lineage[t.name[:-4]] = Lineage(final=tuple(k for _, k in pairs), suppressed=frozenset(t.suppressed))
    return digests, lineage


def _gate_reasons(result, prefix: str) -> list[str]:
    out = []
    if result.refused:
        out.append(f"{prefix}:refused")
    if result.registry_error:
        out.append(f"{prefix}:registry-error")
    out += [f"{prefix}:check:{r.check}:status:{r.status}" for r in result.records
            if r.status not in ("pass", "not_applicable")]
    return out


def _strings(obj, acc: list) -> list:
    """Every string under ``obj``: values and map KEYS at any depth (#149: a value copied into a key is text too)."""
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            acc.append(str(k))
            _strings(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _strings(v, acc)
    return acc


def _self_scan(build: Path, c: Candidate, manifest: dict, context: dict) -> list[str]:
    reasons = []
    expected = sorted([t.name for t in c.tables] + [MANIFEST_FILENAME])
    if sorted(p.name for p in build.iterdir()) != expected or not all(p.is_file() for p in build.iterdir()):
        reasons.append("selfscan:entries")
    reasons += [f"selfscan:manifest:{e}" for e in validate_manifest_file(build)]
    verify = run_checks(build, c.contract, {**context, "phase": "verify"})
    reasons += _gate_reasons(verify, "selfscan")
    reasons += [r.replace("gate:", "selfscan:") for r in _registry_reasons(verify.records)]
    strings = _strings({k: v for k, v in manifest.items() if k != "contract"}, [])
    released = set()
    for t in c.tables:
        released.update(v for v in pd.unique(t.frame.to_numpy(dtype=object).ravel()) if len(v) >= SCAN_MIN_LEN)
    # #80: every source cell value (withheld tables and columns, suppressed rows, raw forms) is scanned too. The
    # one exemption is by identity, not frequency: a manifest string that IS a table or column header name (the
    # writer's structured table/column fields) may contain a source value, e.g. a category inside a column name.
    source = context.get("source", {})
    headers = {stem for stem in source} | {str(col) for df in source.values() for col in df.columns} \
        | {t.name[:-4] for t in c.tables} | {col for t in c.tables for col in t.frame.columns}
    from_source = set()
    for df in source.values():
        for col in df.columns:
            from_source.update(v for v in pd.unique(df[col].to_numpy(dtype=object))
                               if isinstance(v, str) and len(v) >= SCAN_MIN_LEN)
    if _occurs(released, "\x00".join(strings)) or _occurs(from_source, "\x00".join(s for s in strings
                                                                                     if s not in headers)):
        reasons.append("selfscan:manifest-value")
    return reasons


def _occurs(values: set, text: str) -> bool:
    """Any value (each >= SCAN_MIN_LEN long) a substring of ``text``. An n-gram prefilter keeps big kits fast."""
    grams = {text[i:i + SCAN_MIN_LEN] for i in range(len(text) - SCAN_MIN_LEN + 1)}
    return any(v[:SCAN_MIN_LEN] in grams and v in text for v in values)


def _publish_scoring(staging: Path, scoring: Path) -> None:
    os.rename(staging, scoring)


def _rename_release(build: Path, out: Path) -> None:
    os.rename(build, out)  # fails if out exists: never overwrites


def _write_scoring(parent: Path, scoring: Path, files: dict) -> None:
    staging = Path(tempfile.mkdtemp(prefix=f".{scoring.name}.build-", dir=parent))
    try:
        for name, data in sorted(files.items()):
            (staging / name).write_bytes(data)
        _publish_scoring(staging, scoring)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def write_release(candidate: Candidate, out, master_key, kit: Kit, *, context: Mapping | None = None) -> WriteResult:
    """Write ``<out>/`` (protected tables + signed manifest) or refuse. See the package docstring."""
    out = Path(out).absolute()
    scoring = scoring_dir(out)
    if out.exists() or scoring.exists():
        raise WriterError("output folder exists")
    _validate(candidate)
    inputs = _input_digests(kit, candidate.scenario)
    signing_key = manifest_signing_key(master_key)
    context = dict(context or {})
    out.parent.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix=f".{out.name}.build-", dir=out.parent))
    try:
        digests, lineage = _write_tables(build, candidate)
        # the pinned scenario policy, not the candidate, fixes the k target and the QI set (#62)
        reasons = [f"policy:{p}" for p in contract_policy_problems(candidate.scenario, candidate.contract,
                                                                         candidate.narrative.get("fieldJustifications"))]
        gate = run_checks(build, candidate.contract, {**context, "phase": "gate"})
        reasons += _gate_reasons(gate, "gate") + _registry_reasons(gate.records)
        reasons += evidence_for(gate.records, candidate.scenario)[2]
        reasons += justification_reasons(candidate.contract, list(candidate.narrative["fieldJustifications"]))
        manifest = None
        if not reasons:
            manifest, more = assemble_manifest(candidate, gate.records, digests, inputs, signing_key)
            reasons += more
        if manifest is not None and not reasons:
            reasons += [f"manifest:{e}" for e in validate_manifest(manifest)]
        if not reasons:
            (build / MANIFEST_FILENAME).write_bytes(canonical_bytes(manifest))
            reasons += _self_scan(build, candidate, manifest, context)
        reasons = tuple(sorted(set(reasons)))
        if reasons:
            shutil.rmtree(build)
            report = {"status": "refused", "scenario": candidate.scenario, "reasons": list(reasons),
                      "gate": gate.summary()}
            _write_scoring(out.parent, scoring, {REFUSAL_REPORT: canonical_bytes(report)})
            return WriteResult("refused", out, scoring, reasons)
        files = {GATE_REPORT: canonical_bytes(gate.summary()),
                 LINEAGE_FILE: canonical_bytes({s: {"final": list(lin.final), "suppressed": sorted(lin.suppressed)}
                                                for s, lin in lineage.items()})}
        for stem, lin in lineage.items():
            files[f"rowmap_{stem}.csv"] = _csv_bytes(["protected_row", "original_record_id"],
                                                     [[str(i), k] for i, k in enumerate(lin.final)])
        files.update(candidate.scoring_files)
        _write_scoring(out.parent, scoring, files)
        _rename_release(build, out)
        return WriteResult("released", out, scoring, ())
    finally:
        if build.exists():
            shutil.rmtree(build, ignore_errors=True)


def load_lineage(scoring) -> dict:
    """``{table stem: Lineage}`` from a scoring folder, for ticket 08's ``run_scorecard``."""
    from pets_release.manifest import loads_strict

    raw = loads_strict((Path(scoring) / LINEAGE_FILE).read_bytes())
    return {s: Lineage(final=tuple(v["final"]), suppressed=frozenset(v["suppressed"])) for s, v in sorted(raw.items())}
