"""#80: the writer's self-scan refuses a manifest that carries a SOURCE value, not only a released cell value.

Seam: `pets-release run --plan hand`, in-process (``pets_release.cli.main``), on the synthetic minikit. The
fault is planted at one boundary: the narrative ``run`` receives from ``build_narrative`` gets a source value
appended to its fitFor reason (an upstream bug copying a row value into manifest text). Kit reading,
protection, the gate, manifest assembly and the writer's self-scan are production code. Synthetic rows only.

Rule: no source cell value (any table and column: withheld tables, withheld columns, suppressed rows, raw forms of
transformed columns) of at least SCAN_MIN_LEN characters may appear in manifest text (outside `contract`),
however many rows hold it. The only exemption is by identity: a manifest string that is exactly a table or column
header name (the writer's structured table/column fields) is not scanned for source values.

Failure rows (trigger -> result):
  withheld-table free text (clinical_notes.note_text, one hand-made synthetic note) planted in manifest text
                                                     -> was RELEASED; must refuse selfscan:manifest-value
  withheld non-identifier column of a released table (ed_visits.icd10_secondary, a one-row value) planted
                                                     -> was RELEASED; must refuse selfscan:manifest-value
  the same hand-made note held by 5, 6 or 40 note rows, planted (round 2)
                                                     -> RELEASED at 0e0fc58 (frequency exemption); must refuse
  the most common withheld chief_complaint value (many rows), planted (round 2)
                                                     -> RELEASED at 0e0fc58; must refuse
  honest hand release: a source category value occurs inside a column-name string (e.g. inventory[].column)
                                                     -> released (no false positive)
  (identifier values, e.g. patient_name or a raw visit_id, are already refused by producer.original-values in
  the self-scan's verify pass, and raw timestamps by the manifest identifier-shape scan; not rows of this change.)
"""
from __future__ import annotations

import json

import pandas as pd
import pytest
from run_helpers import CREATED, TEST_KEY, build_kit, coarse_qis

from pets_release.writer.core import SCAN_MIN_LEN

NOTE = "Synthetic remark: stable overnight, reviewed by the ward team, plan unchanged."  # hand-made


def _read(kit, table: str) -> pd.DataFrame:
    return pd.read_csv(kit / "data" / "health" / f"{table}.csv", dtype=str, keep_default_na=False, na_filter=False)


def _kit_with_note(tmp_path, rows: int = 1):
    """The synthetic minikit (coarse QIs) with the first ``rows`` notes replaced by the hand-made NOTE."""
    def edit(folder):
        coarse_qis(folder)
        p = folder / "clinical_notes.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[: rows - 1, "note_text"] = NOTE
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    return build_kit(tmp_path / "kit", edit)


def _run(tmp_path, monkeypatch, planted: str | None):
    from pets_release.cli import main
    from pets_release.run import pipeline

    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    out = tmp_path / "out" / "rel"
    if planted is not None:
        real = pipeline.build_narrative

        def leaky(**kw):
            nar = real(**kw)
            nar["fitFor"] = [dict(f, reason=f"{f['reason']} {planted}") for f in nar["fitFor"]]
            return nar

        monkeypatch.setattr(pipeline, "build_narrative", leaky)
    code = main(["run", "--scenario", "HEALTH-S1", "--plan", "hand", "--kit", str(tmp_path / "kit"),
                 "--out", str(out), "--created", CREATED])
    return code, out


def _assert_refused_for(tmp_path, monkeypatch, value):
    code, out = _run(tmp_path, monkeypatch, value)
    assert code == 1
    assert not out.exists()
    report = (out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8")
    assert "selfscan:manifest-value" in json.loads(report)["reasons"]
    assert value not in report  # content-free refusal


def test_withheld_note_in_manifest_refuses(tmp_path, monkeypatch, capsys):
    _kit_with_note(tmp_path)
    _assert_refused_for(tmp_path, monkeypatch, NOTE)
    capsys.readouterr()


def test_one_row_withheld_column_value_in_manifest_refuses(tmp_path, monkeypatch, capsys):
    kit = _kit_with_note(tmp_path)
    counts = _read(kit, "ed_visits")["icd10_secondary"].value_counts()
    value = sorted(v for v in counts.index if counts[v] == 1 and len(v) >= SCAN_MIN_LEN)[0]
    _assert_refused_for(tmp_path, monkeypatch, value)
    capsys.readouterr()


@pytest.mark.parametrize("rows", [5, 6, 40])
def test_repeated_withheld_prose_in_manifest_refuses(tmp_path, monkeypatch, capsys, rows):
    """Frequency never makes a withheld value safe: prose shared by >= 5 note rows still refuses."""
    _kit_with_note(tmp_path, rows)
    _assert_refused_for(tmp_path, monkeypatch, NOTE)
    capsys.readouterr()


def test_common_withheld_chief_complaint_in_manifest_refuses(tmp_path, monkeypatch, capsys):
    """The most common chief complaint (a withheld column, many rows) planted in narrative text refuses."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    counts = _read(kit, "ed_visits")["chief_complaint"].value_counts()
    value = next(v for v in counts.index if len(v) >= SCAN_MIN_LEN)
    assert counts[value] >= 5
    _assert_refused_for(tmp_path, monkeypatch, value)
    capsys.readouterr()


def test_honest_release_with_category_inside_column_name_releases(tmp_path, monkeypatch, capsys):
    kit = _kit_with_note(tmp_path)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    # the exemption really is exercised: a source value occurs inside a manifest `column` string
    names = {e["column"] for e in m["inventory"]}
    hit = False
    for table in ("clinical_notes", "ed_visits", "lab_results", "published_weekly_stats"):
        for _, s in _read(kit, table).items():
            hit |= any(len(v) >= SCAN_MIN_LEN and any(v in n for n in names) for v in s.unique())
    assert hit
