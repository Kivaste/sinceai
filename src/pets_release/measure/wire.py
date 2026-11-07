"""Wire the measurer (19) into the HEALTH-S1 ``run`` (21) without editing ``run/``.

    python -m pets_release.measure.wire <the same arguments as `pets-release run`>

Two passes with the same inputs, key and tool revision (the pipeline is deterministic):
  1. ``run_release`` writes a scratch release; its ``.scoring`` folder supplies lineage and row maps;
  2. ``measure(...)`` scores original-vs-original ("before") and original-vs-release ("after"), adds our
     per-person k summary and the published baselines;
  3. ``run_release`` runs again with ``build_narrative`` returning the same narrative plus the ``measured``
     block, so the final manifest is gated, signed and written by the unchanged writer.
The final tables must be byte-identical to the scratch ones, else the wiring fails (exit 2).
Prints aggregates only. Scratch lives next to ``--out`` as ``<out>.measure/`` and is kept (raw scorecards)."""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from pets_release.cli import UsageError, resolve_run_context
from pets_release.measure import MeasureRejected, measure, person_k_components
from pets_release.run import pipeline
from pets_release.run.context import SCENARIO_SPEC
from pets_release.writer import load_lineage, scoring_dir


def _digests(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.csv"))}


def run_measured(*, kit, scenario: dict, created: str, key_text: str, out, plan_name: str,
                 tool_revision: str):
    """Returns the final ``RunOutcome``. Raises RunError/RunRefused (21) or MeasureRejected (19)."""
    out = Path(out).absolute()
    work = out.with_name(out.name + ".measure")
    if work.exists():
        raise pipeline.RunError("measure scratch folder already exists")
    work.mkdir(parents=True)
    scid = scenario["id"]
    scratch = work / "pass1"
    first = pipeline.run_release(kit=kit, scenario=scenario, created=created, key_text=key_text, out=scratch,
                                 plan_name=plan_name, tool_revision=tool_revision)
    if first.status != "released":
        return first
    sc = first.scoring
    spec = SCENARIO_SPEC[scid]
    rowmaps = {p.stem[len("rowmap_"):]: p for p in sorted(sc.glob("rowmap_*.csv"))}
    lineage = load_lineage(sc)
    dataset = scenario["dataset"]
    person = _person_k_from_release(kit=kit, key_text=key_text, scratch=scratch)
    block = measure(scid, root=kit.root, original_dir=kit.root / "data" / dataset, protected_dir=scratch,
                    rowmaps=rowmaps, lineage=lineage, record_keys=spec["record_keys"], out_dir=work / "scorecards",
                    person_k=person_k_components(person, k=first.suppression["k"]))
    original = pipeline.build_narrative

    def with_measured(**kw):
        n = original(**kw)
        own = n["measured"]["search"]
        n["measured"] = dict(block)
        if own.get("status") == "measured":  # ticket 25: a search run's own measured.search (from its log) stays
            n["measured"]["search"] = own
        return n

    pipeline.build_narrative = with_measured
    try:
        final = pipeline.run_release(kit=kit, scenario=scenario, created=created, key_text=key_text, out=out,
                                     plan_name=plan_name, tool_revision=tool_revision)
    finally:
        pipeline.build_narrative = original
    if final.status == "released" and _digests(final.out) != _digests(scratch):
        left = []
        for d in (final.out, scoring_dir(final.out)):
            try:
                shutil.rmtree(d)
            except OSError:
                left.append(d.name)
            else:
                if d.exists():
                    left.append(d.name)
        if left:
            raise pipeline.RunError("measured release tables differ from the scored scratch release "
                                    "AND cleanup failed: a mismatched release was left behind, delete it by hand")
        raise pipeline.RunError("measured release tables differ from the scored scratch release")
    return final


def _person_k_from_release(*, kit, key_text, scratch):
    """Per-person k of the scratch release, through the producer check's own function and the same
    context ``verify --full`` rebuilds (row maps by pseudonym inversion)."""
    from pets_release.checks.producer.kanon import person_k_values
    from pets_release.manifest import MANIFEST_FILENAME, loads_strict
    from pets_release.pseudonym import MasterKey
    from pets_release.run.context import verify_context

    manifest = loads_strict((scratch / MANIFEST_FILENAME).read_bytes())
    ctx = verify_context(kit, MasterKey.from_text(key_text), scratch)
    return person_k_values(scratch, manifest["contract"], ctx)


def main(argv: list[str]) -> int:
    try:
        ctx = resolve_run_context(argv)
    except UsageError as e:
        print(f"measure.wire: {e}", file=sys.stderr)
        return 2
    from pets_release.verify import current_tool_revision

    rev = current_tool_revision()
    if rev is None:
        print("measure.wire: tool revision unavailable (git HEAD)", file=sys.stderr)
        return 2
    a = ctx.args
    try:
        res = run_measured(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key,
                           out=a.out, plan_name=a.plan or "hand", tool_revision=rev)
    except Exception as e:  # noqa: BLE001  content-free: class name and our own short messages only
        own = isinstance(e, (pipeline.RunError, MeasureRejected))  # only our own content-free messages
        print(f"measure.wire: {type(e).__name__}" + (f": {str(e)[:200]}" if own else ""), file=sys.stderr)
        return 2
    print(f"{'RELEASED' if res.status == 'released' else 'REFUSED'}: {res.out.name} (measured)")
    return 0 if res.status == "released" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
