"""Producer-side attribute-inference lift (D64, #157): the bound the search enforces on bounded sensitive attributes.

The release tool never imports the attacker (#138: it runs only as a child via the pinned launcher), so this is a
producer-side implementation of #139's red-team estimator (``pets_attacker.redteam.attribute_inference``):

  targets     the released rows with a non-blank value of the attribute, a seeded sample (seed 0) of at most 3000,
              as the red team's sampling frame;
  attacker    knows the target's QIs and predicts the most common released value (ties: the smallest string)
              among the rows that match them best;
  baseline    the release's most common value of the attribute, guessed for every target;
  lift        inference_rate / baseline_rate.

The one difference: the red team scores rows with Fellegi-Sunter over interval overlaps (the age tolerance can
merge neighbouring bands) and treats a blank QI cell as a wildcard; here the best rows are exactly the target's
own equivalence class on every released QI of the policy (a superset of the red team's background QIs). On the
same release this attacker is at least as sharp on small classes (tested against #139's numbers on a synthetic
fixture, ``tests/minimiser/test_attr_lift.py``). Aggregates only: nothing here logs or returns a value.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

MAX_SAMPLE = 3000  # the red team's sampling frame (pets_attacker.personas.MAX_SAMPLE)
SEED = 0
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


def _sample(n: int) -> np.ndarray:
    rows = np.arange(n)
    if n > MAX_SAMPLE:
        rows = np.sort(np.random.default_rng(SEED).choice(n, MAX_SAMPLE, replace=False))
    return rows


def measure(df: pd.DataFrame, qcols: list, column: str) -> dict:
    """``{n_targets, inference_rate, baseline_rate, lift}`` for ``column`` of the released table ``df`` against an
    attacker who knows ``qcols``. ``lift`` is None when it cannot be measured (no target, or a zero base rate with a
    non-zero inference rate is ``inf``); callers treat None as over the bound (fail closed)."""
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
    for r in _sample(len(df)):
        truth = cells[r]
        if not truth:
            continue
        n += 1
        ok += guess[keys[r]] == truth
        b += base == truth
    if n == 0:
        return {"n_targets": 0, "inference_rate": None, "baseline_rate": None, "lift": None}
    inf, bas = ok / n, b / n
    lift = (inf / bas) if bas > 0 else (math.inf if inf > 0 else 1.0)
    return {"n_targets": n, "inference_rate": round(inf, 6), "baseline_rate": round(bas, 6),
            "lift": round(lift, 6) if math.isfinite(lift) else None}
