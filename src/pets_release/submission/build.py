"""Build ``pets_submission/``: unseen labels, CS eval redactions and spans, and verified protected tables with
their row maps, one sub-folder per dataset. Written outside the public repo, atomically, byte-for-byte reproducibly.

Failure rows (trigger -> refusal code): see tests/submission. Nothing is written on a refusal; the temporary
folders are removed. Output is content-free: file names, digests and aggregate numbers only.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pets_release.kit import Kit, KitError
from pets_release.kiteval import RowMapRejected, ScorecardRejected, validate_row_map
from pets_release.manifest import MANIFEST_FILENAME, canonical_bytes, loads_strict, required_assertions
from pets_release.pseudonym import MasterKey
from pets_release.submission import guards
from pets_release.submission.cs_eval import cs_eval_outputs
from pets_release.submission.errors import SubmissionRefused
from pets_release.submission.unseen import unseen_labels
from pets_release.verify import VerifyUsageError, verify_release
from pets_release.writer import load_lineage, scoring_dir

UNSEEN_FILE = "unseen_field_labels.csv"
CS_REDACTED_FILE = "customer_service_eval_redacted.csv"
CS_SPANS_FILE = "customer_service_eval_spans.jsonl"
INDEX_FILE = "submission_index.json"


@dataclass(frozen=True)
class SubmissionResult:
    out: Path
    scoring: Path
    files: dict  # relative posix path -> sha256 of every file in ``out``
    datasets: tuple  # one aggregate dict per protected dataset
    index: dict


@dataclass(frozen=True)
class _Release:
    dataset: str
    scenario: str
    source: Path
    scoring: Path
    manifest: dict
    tables: tuple  # table file names, sorted
    lineage: dict


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _default_scorecard():
    from pets_release.kiteval import run_scorecard

    return run_scorecard


def _read_release(kit: Kit, master: MasterKey, src: Path) -> _Release:
    from pets_release.run.context import verify_context

    src = guards.refuse_forbidden_source(src)
    sc = guards.refuse_forbidden_source(scoring_dir(src))
    if not src.is_dir() or not sc.is_dir():
        raise SubmissionRefused("release_missing")
    try:
        ctx = verify_context(kit, master, src)
    except Exception:  # noqa: BLE001 - content-free; an unknown state is a refusal
        ctx = None
    try:
        report = verify_release(src, full=True, kit=kit, master_key=master, context=ctx)
    except VerifyUsageError:
        raise SubmissionRefused("release_not_verified") from None
    if not report.ok or ctx is None:
        raise SubmissionRefused("release_not_verified")
    manifest = loads_strict((src / MANIFEST_FILENAME).read_bytes())
    scenario = manifest["release"]["scenario"]
    # Export assertions: exactly the scenario's required set, each the literal False (verify re-ran the checks).
    asserted = manifest.get("exportAssertions")
    if (not isinstance(asserted, dict) or sorted(asserted) != sorted(required_assertions(scenario))
            or any(v is not False for v in asserted.values())):
        raise SubmissionRefused("release_not_verified")
    try:
        dataset = kit.scenario(scenario)["dataset"]
    except (KitError, KeyError):
        raise SubmissionRefused("release_not_verified") from None
    tables = tuple(sorted(manifest["bindings"]["files"]))
    if not tables or sorted(p.name for p in src.iterdir()) != sorted([*tables, MANIFEST_FILENAME]):
        raise SubmissionRefused("release_not_verified")
    stems = {t[:-4] for t in tables}
    maps = {p.stem[len("rowmap_"):] for p in sc.glob("rowmap_*.csv")}
    if maps - stems:
        raise SubmissionRefused("rowmap_unexpected")
    if stems - maps or any(not (sc / f"rowmap_{s}.csv").is_file() for s in stems):
        raise SubmissionRefused("rowmap_missing")
    try:
        lineage = load_lineage(sc)
    except (OSError, ValueError, KeyError, TypeError):
        raise SubmissionRefused("rowmap_invalid") from None
    if set(lineage) != stems:
        raise SubmissionRefused("rowmap_invalid")
    derived = ctx.get("rowmaps", {})
    for stem in sorted(stems):
        _check_row_map(sc / f"rowmap_{stem}.csv", src / f"{stem}.csv", lineage[stem], derived.get(stem))
    return _Release(dataset, scenario, src, sc, manifest, tables, lineage)


def _check_row_map(path: Path, table: Path, lineage, derived) -> None:
    """The row map must pass the adapter's validation against the writer's lineage, and, where the producer
    context can recompute it from kit + key, equal that recomputation exactly."""
    rows = len(pd.read_csv(table, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8"))
    try:
        validate_row_map(path, protected_rows=rows, source_keys=set(lineage.final) | set(lineage.suppressed),
                         expected_lineage=lineage)
        if derived is not None:
            got = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
            if not got.reset_index(drop=True).equals(derived.reset_index(drop=True)):
                raise RowMapRejected("derived_mismatch")
    except (RowMapRejected, OSError, ValueError):
        raise SubmissionRefused("rowmap_invalid") from None


def build_submission(*, kit: Kit, releases: Sequence, out, master: MasterKey,
                     scorecard: Callable | None = None, passes: Sequence | None = None) -> SubmissionResult:
    """Build the submission at ``out`` (and ``<out>.scoring/`` with scorecard output and the index) or raise
    SubmissionRefused. ``scorecard`` replaces the out-of-process evaluator (tests only; the CLI never passes it)."""
    out = Path(out).absolute()
    scoring = scoring_dir(out)
    guards.refuse_inside_public_repo(out)
    if out.exists() or scoring.exists():
        raise SubmissionRefused("out_exists")
    if not releases:
        raise SubmissionRefused("no_release")
    scorecard = scorecard or _default_scorecard()
    parsed = [_read_release(kit, master, Path(r)) for r in releases]
    if len({r.dataset for r in parsed}) != len(parsed):
        raise SubmissionRefused("duplicate_dataset")
    parsed.sort(key=lambda r: r.dataset)
    labels, unseen_counts = unseen_labels(kit)
    redacted, spans, cs_counts = cs_eval_outputs(kit, passes)

    out.parent.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix=f".{out.name}.build-", dir=out.parent))
    sbuild = Path(tempfile.mkdtemp(prefix=f".{out.name}.scoring-build-", dir=out.parent))
    try:
        files: dict[str, bytes] = {UNSEEN_FILE: labels, CS_REDACTED_FILE: redacted, CS_SPANS_FILE: spans}
        for r in parsed:
            for t in r.tables:
                files[f"{r.dataset}/{t}"] = (r.source / t).read_bytes()
                stem = t[:-4]
                files[f"{r.dataset}/rowmap_{stem}.csv"] = (r.scoring / f"rowmap_{stem}.csv").read_bytes()
            files[f"{r.dataset}/{MANIFEST_FILENAME}"] = (r.source / MANIFEST_FILENAME).read_bytes()
        for rel, data in sorted(files.items()):
            p = build / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        guards.check_layout(build, files)
        guards.scan_key_material(build, master)
        for r in parsed:  # the shipped bytes are the bytes the manifest bound
            for t in r.tables:
                if _sha(files[f"{r.dataset}/{t}"]) != r.manifest["bindings"]["files"][t]:
                    raise SubmissionRefused("release_not_verified")
        summaries = [_score(kit, r, build, sbuild, scorecard) for r in parsed]
        digests = {rel: _sha((build / rel).read_bytes()) for rel in sorted(files)}
        index = {"files": digests,
                 "datasets": [{"dataset": r.dataset, "scenario": r.scenario, "tables": [t[:-4] for t in r.tables],
                               "scorecard": s} for r, s in zip(parsed, summaries, strict=True)],
                 "customerServiceEval": cs_counts, "unseen": unseen_counts}
        (sbuild / INDEX_FILE).write_bytes(canonical_bytes(index))
        os.rename(sbuild, scoring)
        try:
            os.rename(build, out)
        except OSError:
            shutil.rmtree(scoring, ignore_errors=True)
            raise
        return SubmissionResult(out, scoring, digests, tuple(index["datasets"]), index)
    finally:
        for d in (build, sbuild):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)


def _score(kit: Kit, r: _Release, build: Path, sbuild: Path, scorecard: Callable) -> dict:
    """Run the scorecard on exactly the shipped bytes: a row-map-free copy of the dataset folder, with every
    table's row map passed explicitly."""
    with tempfile.TemporaryDirectory(prefix="pets-stage-") as tmp:
        stage = Path(tmp) / r.dataset
        stage.mkdir()
        for t in (*r.tables, MANIFEST_FILENAME):
            shutil.copyfile(build / r.dataset / t, stage / t)
        rowmaps = {t[:-4]: build / r.dataset / f"rowmap_{t[:-4]}.csv" for t in r.tables}
        try:
            summary = scorecard(kit.root / "data" / r.dataset, stage, scenario=r.scenario, root=kit.root,
                                rowmaps=rowmaps, lineage=r.lineage, out_dir=sbuild / r.dataset)
        except RowMapRejected:
            raise SubmissionRefused("rowmap_invalid") from None
        except ScorecardRejected:
            raise SubmissionRefused("scorecard_rejected") from None
        except Exception:  # noqa: BLE001 - an errored evaluator is a refusal, never a pass; no values leak
            raise SubmissionRefused("scorecard_error") from None
    return summary
