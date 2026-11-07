"""#80: the writer's self-scan refuses a manifest that carries a SOURCE value, not only a released cell value.

Seam: `pets-release run --plan hand`, in-process (``pets_release.cli.main``), on the synthetic minikit. The
fault is planted at one boundary: the narrative ``run`` receives from ``build_narrative`` gets a source value
appended to its fitFor reason (an upstream bug copying a row value into manifest text). Kit reading,
protection, the gate, manifest assembly and the writer's self-scan are production code. Synthetic rows only.

Rule: a source value (any table and column: withheld tables, withheld columns, suppressed rows, raw forms of
transformed columns) of at least SCAN_MIN_LEN characters, held by fewer than k source rows of its column, must
not appear in manifest text (outside `contract`). A value shared by k or more rows of its column is a category,
not row content, and is not scanned (an honest manifest names categories, e.g. inside column names).

Failure rows (trigger -> result):
  withheld-table free text (clinical_notes.note_text, one hand-made synthetic note) planted in manifest text
                                                     -> today RELEASED; must refuse selfscan:manifest-value
  withheld non-identifier column of a released table (ed_visits.icd10_secondary, a one-row value) planted
                                                     -> today RELEASED; must refuse selfscan:manifest-value
  honest hand release whose manifest text contains a withheld category value held by >= k rows
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

K = 5  # the HEALTH-S1 policy's k (asserted on the honest release's contract below)
NOTE = "Synthetic remark: stable overnight, reviewed by the ward team, plan unchanged."  # hand-made


def _read(kit, table: str) -> pd.DataFrame:
    return pd.read_csv(kit / "data" / "health" / f"{table}.csv", dtype=str, keep_default_na=False, na_filter=False)


def _kit_with_note(tmp_path):
    def edit(folder):
        coarse_qis(folder)
        p = folder / "clinical_notes.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[0, "note_text"] = NOTE
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    return build_kit(tmp_path / "kit", edit)


def _one_row_value(kit, table: str, column: str) -> str:
    counts = _read(kit, table)[column].value_counts()
    return sorted(v for v in counts.index if counts[v] == 1 and len(v) >= SCAN_MIN_LEN)[0]


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


@pytest.mark.parametrize(("table", "column"), [
    ("clinical_notes", "note_text"),   # withheld table, free text
    ("ed_visits", "icd10_secondary"),  # withheld non-identifier column of a released table
])
def test_planted_source_value_in_manifest_refuses(tmp_path, monkeypatch, capsys, table, column):
    kit = _kit_with_note(tmp_path)
    value = NOTE if column == "note_text" else _one_row_value(kit, table, column)
    code, out = _run(tmp_path, monkeypatch, value)
    capsys.readouterr()
    assert code == 1
    assert not out.exists()
    report = (out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8")
    assert "selfscan:manifest-value" in json.loads(report)["reasons"]
    assert value not in report  # content-free refusal


def test_honest_release_with_category_in_manifest_text_releases(tmp_path, monkeypatch, capsys):
    kit = _kit_with_note(tmp_path)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 0
    m = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))
    assert m["contract"]["k"] == K
    text = json.dumps({k: v for k, v in m.items() if k != "contract"}, ensure_ascii=False)
    # the case really is exercised: some withheld category value (>= k rows) occurs in the manifest text
    shared = False
    for table in ("clinical_notes", "ed_visits"):
        for c, s in _read(kit, table).items():
            shared |= any(len(v) >= SCAN_MIN_LEN and n >= K and v in text for v, n in s.value_counts().items())
    assert shared
