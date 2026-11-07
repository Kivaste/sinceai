"""#149 (folded Spec/Gemini finding 5): the manifest source-value scan is a registered gate check, so
``verify --full`` re-runs it on a signed release instead of trusting the writer alone.

Seam: the real ``pets-release verify --full`` CLI (subprocess) on a release built by the real ``pets-release run``
CLI on the synthetic run minikit. The manifest is edited after release (as a buggy or tampered producer would) and
re-signed with the test key, so signature, digests and identifier-shape checks all still pass; only the source-value
scan can see the plant. Synthetic rows only.

Rule: ``producer.manifest-source-values`` is registered, runs in the gate and in ``verify --full``, and fails on a
source cell value (>= SCAN_MIN_LEN characters, case- and whitespace-folded) anywhere in the manifest, map keys
included.

Rows (trigger -> result):
  unchanged real release                                  -> verify --full exit 0; the check re-runs and passes
  a withheld chief_complaint value, UPPER-cased with doubled spaces, planted in fitFor[0].reason, re-signed
                                                          -> was exit 0 at 4f05153; must exit 1 with a
                                                             producer.manifest-source-values fail line, value
                                                             not echoed
  a withheld clinical_notes.note_type value (paramName-shaped) planted as a pets[0].params KEY, re-signed
                                                          -> same
"""
from __future__ import annotations

import re

import pandas as pd

CHECK = "producer.manifest-source-values"


def _source(real_bed, table: str, column: str) -> pd.Series:
    return pd.read_csv(real_bed.kit / "data" / "health" / f"{table}.csv", dtype=str, keep_default_na=False,
                       na_filter=False)[column]


def _fail_line(stdout: str) -> bool:
    return any(x.startswith(f"check {CHECK} [producer]") and ": fail " in x for x in stdout.splitlines())


def test_unchanged_release_reruns_the_check(real_bed, verify_cli):
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 0, r.stdout
    assert CHECK in real_bed.release.joinpath("privacy_manifest.json").read_text(encoding="utf-8")


def test_folded_withheld_value_in_manifest_text_fails_verify_full(real_bed, tb, verify_cli):
    value = sorted((v for v in _source(real_bed, "ed_visits", "chief_complaint").unique() if len(v) >= 6),
                   key=lambda v: (-len(v), v))[0]
    planted = "  ".join(value.upper().split(" "))
    m = tb.load(real_bed.release)
    m["fitFor"][0]["reason"] = f"{m['fitFor'][0]['reason']} {planted}"
    real_bed.resign(m)
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert _fail_line(r.stdout), r.stdout
    assert value not in r.stdout + r.stderr and planted not in r.stdout + r.stderr


def test_withheld_value_as_map_key_fails_verify_full(real_bed, tb, verify_cli):
    shaped = re.compile(r"[A-Za-z][A-Za-z0-9_]{5,63}")
    # clinical_notes is a withheld table in HEALTH-S1; note_type is a non-identifier category column
    value = sorted(v for v in _source(real_bed, "clinical_notes", "note_type").unique() if shaped.fullmatch(v))[0]
    m = tb.load(real_bed.release)
    m["pets"][0]["params"][value] = 1
    real_bed.resign(m)
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert _fail_line(r.stdout), r.stdout
    assert value not in r.stdout + r.stderr
