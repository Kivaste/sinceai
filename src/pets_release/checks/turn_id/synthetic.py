"""``turn-id-synthetic``: the released ``turns.turn_id`` is a synthetic record key with no
person or conversation information (D21; rules in ``_rules``).

Applies only when the contract releases ``turns.csv/turn_id`` (else ``not_applicable``, e.g. for
HEALTH-S1). Producer scope; context (missing -> ``not_run``, which refuses):
  source:       {table: DataFrame (dtype=str)} original tables (``turns``, ``conversations``)
  identifiers:  [{table, column}] source identifier columns (ticket 11's key)

The CS-S1 glue (``pets_release.cs_s1``) runs the same rules on the candidate before choosing
between keeping ``turn_id`` and the release-scope pseudonym fallback.
"""
from __future__ import annotations

from pets_release.checks.records import Outcome, Violation, locations
from pets_release.checks.registry import register

from . import _rules

NAME = "turn-id-synthetic"
VERSION = "1.0.0"
FILE, COLUMN = "turns.csv", "turn_id"


def assess(ids, conv, source, identifiers) -> dict[str, int]:
    """Same rules on candidate columns (before release): ``{label: rows with a hit}``; empty = pass."""
    return {label: len(rows) for label, rows in sorted(_rules.evaluate(ids, conv, source, list(identifiers)).items())}


@register(name=NAME, version=VERSION, scope="producer", unit="turns", applies_to=(f"column:{FILE}/{COLUMN}",))
def run(release, contract, context) -> Outcome:
    context = context or {}
    spec = (contract or {}).get("files", {}).get(FILE)
    if spec is None or COLUMN not in spec["columns"]:
        return Outcome.not_applicable()
    if context.get("source") is None or context.get("identifiers") is None:
        return Outcome.not_run()
    if FILE not in release.csv_files:
        raise _rules.RuleError("released turns file missing")
    table = release.table(FILE)
    header = list(table.header)
    if COLUMN not in header or "conversation_id" not in header:
        raise _rules.RuleError("released turns lacks turn_id or conversation_id")
    frame = table.frame
    ids = frame.iloc[:, header.index(COLUMN)]
    conv = frame.iloc[:, header.index("conversation_id")]
    token = any(t.get("table") == "turns" and t.get("column") == COLUMN for t in (contract.get("tokens") or []))
    hits = _rules.evaluate(ids, conv, context["source"], list(context["identifiers"]), token_column=token)
    viol = tuple(Violation(NAME, label, "high", FILE, COLUMN, len(rows), locations(rows))
                 for label, rows in sorted(hits.items()))
    return Outcome(n=len(ids), violations=viol)
