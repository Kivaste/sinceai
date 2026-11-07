"""Release writer with signed manifest (ticket 16).

Public API::

    from pets_release.writer import Candidate, ProtectedTable, write_release, scoring_dir, load_lineage

    res = write_release(candidate, out_dir, master_key, kit, context={...})   # -> WriteResult
    res.status            # "released" | "refused"
    res.reasons           # sorted content-free codes (empty when released)

What it does, in order:
  1. Refuses to start (``WriterError``, nothing written) if ``<out>/`` or ``<out>.scoring/`` exists, the candidate
     is malformed (non-str cells, lineage not one unique source key per row, narrative keys not exactly
     ``NARRATIVE_KEYS``), or the kit has no dataset for the scenario. ``bindings.inputs`` is
     ``kit.input_digests(dataset)``: every table of the scenario's dataset, withheld tables included.
  2. Writes each protected table, rows sorted, into a hidden build folder ``.<out>.build-*`` next to ``<out>``.
  3. Gate: ticket 04's ``run_checks(build, contract, {**context, "phase": "gate"})`` over exactly the registry.
     There is no way to pass other checks; the records must equal the registry's (name, version, scope, unit),
     else ``gate:registry-mismatch`` refuses. Producer checks read their inputs from ``context`` (source tables,
     row maps, keys, ...); absent inputs mean ``not_run``, which refuses.
  4. Evidence (``assemble.evidence_for``): each of the scenario's required assertions needs its
     ``ASSERTION_CHECKS`` record with status pass, 0 hits, n >= 1 and 02's scope/unit. Otherwise refuse. The
     assertion value is the literal ``False``; there is no other code path. ``not_applicable`` records are listed in
     ``gate.checks`` (n 0) and never back an assertion.
  5. Field-justification tie: every released contract column has a released justification and vice versa.
  6. Assembles the manifest (bindings: per-file SHA-256, input digests, tool revision, check versions, lexicon
     digests, contract digest; ``releaseScopeId``), signs it with ticket 06's ``manifest_signing_key(master)``
     (HMAC-SHA256 over 02's canonical bytes without ``signature``) and validates it with 02's validator.
  7. Self-scan: folder holds only the tables + manifest; 02's file validator (canonical bytes); the gate again in
     ``verify`` phase (bindings now checked); no released cell value of >= 6 chars appears in manifest text
     outside ``contract``.
  8. Publishes ``<out>.scoring/`` (``rowmap_<table>.csv``, ``lineage.json``, ``gate_report.json``, the
     candidate's ``scoring_files``), then renames the build folder to ``<out>/`` (one ``os.rename``).

On refusal nothing is published: ``<out>.scoring/refusal_report.json`` holds the reasons and the gate's aggregate
summary (check names, statuses, counts, file/column names; no values, no row locations). A crash or exception at
any point before the final rename leaves no ``<out>/``.

``load_lineage(scoring)`` returns ``{table stem: Lineage(final, suppressed)}`` (ticket 08's type) for
``run_scorecard``.
"""
from pets_release.writer.core import (
    Candidate,
    Lineage,
    ProtectedTable,
    WriterError,
    WriteResult,
    load_lineage,
    scoring_dir,
    table_bytes,
    write_release,
)

__all__ = ["Candidate", "Lineage", "ProtectedTable", "WriteResult", "WriterError", "load_lineage", "scoring_dir",
           "table_bytes", "write_release"]
