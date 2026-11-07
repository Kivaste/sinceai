"""Candidate-input digests for the purpose-check cache.

A purpose check's cached result is reused only when the digest of every protected column the check reads
is unchanged. ``KIT_READ_SETS`` lists those columns for the kit tasks the scenarios use, read from the
pets-eval task source (kit 1.0.0): every health task calls ``derive`` on ``ed_visits``, which reads the
columns in ``_HEALTH_DERIVE``; H-U7 also joins ``lab_results``. A task with no entry is digested over
every column of every protected table, so an unknown task is never served a stale result. The final
re-check after suppression never uses the cache, so a wrong entry here cannot reach a release.

Digests are of transformed values and stay in memory; only the hex digest of a whole candidate is logged.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

import pandas as pd

_HEALTH_DERIVE = (
    "age", "age_band", "arrival_mode", "arrival_ts", "date_of_birth", "diagnosis_group", "discharge_ts",
    "disposition", "heart_rate", "icd10_primary", "los_minutes", "municipality", "pain_nrs", "patient_hetu",
    "readmit_30d", "resp_rate", "sex", "spo2", "systolic_bp", "temp_c", "triage", "visit_id",
)

KIT_READ_SETS: dict[str, dict[str, tuple[str, ...]]] = {
    "H-U2": {"ed_visits": _HEALTH_DERIVE},
    "H-U4": {"ed_visits": _HEALTH_DERIVE},
    "H-U6": {"ed_visits": _HEALTH_DERIVE},
    "H-U8": {"ed_visits": _HEALTH_DERIVE},
    "H-U7": {"ed_visits": _HEALTH_DERIVE, "lab_results": ("test_code", "value", "visit_id")},
}

_ABSENT = "\x00absent"


def series_digest(s: pd.Series) -> str:
    """SHA-256 over the index and values of one column (canonical JSON)."""
    vals = ["" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v) for v in s.tolist()]
    idx = [str(i) for i in s.index.tolist()]
    return hashlib.sha256(json.dumps([idx, vals], separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def input_digest(task: str, read_sets: Mapping, col_digest) -> str:
    """Digest of the columns ``task`` reads. ``col_digest(table, column)`` -> hex or ``None`` when absent;
    ``col_digest.tables()`` lists (table, [columns]) of the whole candidate for unknown tasks."""
    spec = read_sets.get(task)
    if spec is None:
        parts = [[t, c, col_digest(t, c)] for t, cols in col_digest.tables() for c in cols]
        parts.append(["*", "*", "all"])
    else:
        parts = [[t, c, col_digest(t, c) or _ABSENT] for t in sorted(spec) for c in sorted(spec[t])]
        parts.append(["*", "tables", sorted(t for t, _ in col_digest.tables())])
    blob = json.dumps([task, parts], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()
