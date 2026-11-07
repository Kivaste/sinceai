"""Producer-side attribute-inference lift (D64, #157): the bound the search enforces on bounded sensitive attributes.

The release tool never imports the attacker (#138: it runs only as a child via the pinned launcher), so this is a
producer-side implementation of #139's red-team attribute-inference estimator (the attacker package's
``redteam.attribute_inference``; named here without importing it):

  targets     EVERY released row with a non-blank value of the attribute (the population, not the red team's
              seeded sample of at most 3000: that sample is drawn over the released row order, which follows the
              keyed tokens and so changes with the release key; the population measure is independent of row
              order and key, so the bound check is deterministic and not a sampling draw);
  attacker    knows the target's QIs and predicts the most common released value (ties: the smallest string)
              among the rows that match them best;
  baseline    the release's most common value of the attribute, guessed for every target;
  lift        inference_rate / baseline_rate.

The one difference: the red team scores rows with Fellegi-Sunter over interval overlaps (the age tolerance can
merge neighbouring bands) and treats a blank QI cell as a wildcard; here the best rows are exactly the target's
own equivalence class on every released QI of the policy (a superset of the red team's background QIs). Where the
two coincide (every QI released, no blank cell, no band edge within the age tolerance, at most 3000 targets) they
give the same targets, inference rate and base rate (``tests/minimiser/test_attr_lift.py``, against the red team
itself). Aggregates only: nothing here logs or returns a value.
"""

from __future__ import annotations

import math
import re

import pandas as pd

from pets_release.ladders import WITHHELD, output_column

_MASKED = re.compile(r"^[\*x#?\-_]*$", re.IGNORECASE)  # the red team's blank rule (masked cells are blank)


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    s = str(v).strip()
    return "" if s == "" or _MASKED.match(s) else s


def _mode(values) -> str | None:
    counts: dict = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    return min(counts, key=lambda v: (-counts[v], v)) if counts else None


def released_qcols(policy, plan, table: str) -> list:
    """Output names of the policy QIs of ``table`` (not join-derived) that ``plan`` releases: what the attacker
    knows. One rule for the search and the run's recorded lift step."""
    by_key = {(e["table"], e["column"]): e for e in plan}
    return [output_column(by_key[(q["table"], q["column"])]) for q in policy.qi
            if q["table"] == table and not q.get("join_via") and by_key[(q["table"], q["column"])]["rung"] != WITHHELD]


def measure(df: pd.DataFrame, qcols: list, column: str) -> dict:
    """``{n_targets, inference_rate, baseline_rate, lift}`` for ``column`` of the released table ``df`` against an
    attacker who knows ``qcols``. ``lift`` is None when it cannot be measured (no target, or a zero base rate with a
    non-zero inference rate); callers treat None as over the bound (fail closed)."""
    df = df.reset_index(drop=True)
    cells = [_cell(v) for v in df[column].tolist()]
    if qcols:
        keys = list(zip(*[[_cell(v) for v in df[q].tolist()] for q in sorted(qcols)]))
    else:
        keys = [()] * len(df)
    groups: dict = {}
    for k, v in zip(keys, cells):
        groups.setdefault(k, []).append(v)
    guess = {k: _mode(v) for k, v in groups.items()}
    base = _mode(cells)
    n = ok = b = 0
    for key, actual in zip(keys, cells):  # every row: independent of row order and of the release key
        if not actual:
            continue
        n += 1
        ok += guess[key] == actual
        b += base == actual
    if n == 0:
        return {"n_targets": 0, "inference_rate": None, "baseline_rate": None, "lift": None}
    rate, bas = ok / n, b / n
    # a zero base rate with any inference has no finite lift: None, which the search counts as over the bound
    lift = round(rate / bas, 6) if bas > 0 else (None if rate > 0 else 1.0)
    return {"n_targets": n, "inference_rate": round(rate, 6), "baseline_rate": round(bas, 6), "lift": lift}
