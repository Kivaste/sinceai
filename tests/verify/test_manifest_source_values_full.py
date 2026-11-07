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
  (r2) own kit with one withheld note cell equal to a column name; its honest release verifies; that value
  re-signed as the whole fitFor[0].reason                 -> was exit 0 at 19870a2 (header exemption at any path);
                                                             must exit 1 with the check's fail line
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
    value = min((v for v in _source(real_bed, "ed_visits", "chief_complaint").unique() if len(v) >= 6),
                key=lambda v: (-len(v), v))
    planted = "  ".join(value.upper().split(" "))
    m = tb.load(real_bed.release)
    m["fitFor"][0]["reason"] = f"{m['fitFor'][0]['reason']} {planted}"
    real_bed.resign(m)
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert _fail_line(r.stdout), r.stdout
    assert value not in r.stdout + r.stderr and planted not in r.stdout + r.stderr


def test_header_equal_source_value_in_free_text_fails_verify_full(tmp_path, tb, verify_cli):
    """#149 r2: a source value equal to a column name, re-signed into fitFor[0].reason as the whole string, fails
    verify --full (the header exemption holds only at structural header paths). Own kit: one withheld note cell
    is the column name; the honest release of that kit verifies first."""
    import sys

    from tests.verify.conftest import ROOT, RealBed

    sys.path.insert(0, str(ROOT / "tests" / "run"))
    from run_helpers import build_kit, cli, coarse_qis, run_args

    header = "chief_complaint"

    def edit(folder):
        coarse_qis(folder)
        p = folder / "clinical_notes.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[0, "note_text"] = header
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    kit = build_kit(tmp_path / "kit", edit)
    out = tmp_path / "out" / "rel"
    proc = cli(*run_args(kit, out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bed = RealBed(kit, out)
    assert verify_cli("--full", "--kit", kit, out, env=bed.env()).returncode == 0
    m = tb.load(out)
    m["fitFor"][0]["reason"] = header
    bed.resign(m)
    r = verify_cli("--full", "--kit", kit, out, env=bed.env())
    assert r.returncode == 1, r.stdout
    assert _fail_line(r.stdout), r.stdout


def test_withheld_value_as_map_key_fails_verify_full(real_bed, tb, verify_cli):
    shaped = re.compile(r"[A-Za-z][A-Za-z0-9_]{5,63}")
    # clinical_notes is a withheld table in HEALTH-S1; note_type is a non-identifier category column
    value = min(v for v in _source(real_bed, "clinical_notes", "note_type").unique() if shaped.fullmatch(v))
    m = tb.load(real_bed.release)
    m["pets"][0]["params"][value] = 1
    real_bed.resign(m)
    r = verify_cli("--full", "--kit", real_bed.kit, real_bed.release, env=real_bed.env())
    assert r.returncode == 1, r.stdout
    assert _fail_line(r.stdout), r.stdout
    assert value not in r.stdout + r.stderr
