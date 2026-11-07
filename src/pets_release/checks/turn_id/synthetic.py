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

from types import SimpleNamespace

import pandas as pd

from pets_release.checks import registry
from pets_release.checks.records import Outcome, Violation, locations
from pets_release.checks.registry import register

from . import _rules

NAME = "turn-id-synthetic"
VERSION = "1.1.0"
FILE, COLUMN = "turns.csv", "turn_id"


def assess(ids, conv, source, identifiers) -> dict[str, int]:
    """Execute the registered prerequisite before keep; unavailable/unknown selects the fallback.

    This is a plan-selection assessment, not gate evidence. The gate executes the check again on
    the written candidate. No on-disk assessment or previous record is consulted.
    """
    n = max(1, len(ids))
    try:
        selected = [c for c in registry.all_checks() if c.name == NAME]
        if len(selected) != 1:
            return {"unavailable": n}
        check = selected[0]
        if (check.version, check.scope, check.unit) != (VERSION, "producer", "turns"):
            return {"unavailable": n}
        frame = pd.DataFrame({COLUMN: ids.reset_index(drop=True),
                              "conversation_id": conv.reset_index(drop=True)})
        table = SimpleNamespace(header=tuple(frame.columns), frame=frame)
        release = SimpleNamespace(csv_files=(FILE,), table=lambda name: table)
        contract = {"files": {FILE: {"columns": {COLUMN: {}, "conversation_id": {}}}}, "tokens": []}
        out = check.run(release, contract, {"source": source, "identifiers": list(identifiers)})
        if (not isinstance(out, Outcome) or out.skipped or out.inapplicable
                or type(out.n) is not int or out.n != len(ids) or out.n == 0):
            return {"undetermined": n}
        hits: dict[str, int] = {}
        for violation in out.violations:
            if (not isinstance(violation, Violation) or violation.check != NAME
                    or type(violation.count) is not int or violation.count < 1):
                return {"undetermined": n}
            hits[violation.label] = hits.get(violation.label, 0) + violation.count
        return dict(sorted(hits.items()))
    except Exception:  # noqa: BLE001 (check errors never expose values or permit raw keep)
        return {"unavailable": n}


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
