"""#80: the writer's self-scan refuses a manifest that carries a SOURCE value, not only a released cell value.

Seam: `pets-release run --plan hand`, in-process (``pets_release.cli.main``), on the synthetic minikit. The
fault is planted at one boundary: the narrative ``run`` receives from ``build_narrative`` gets a source value
appended to its fitFor reason (an upstream bug copying a row value into manifest text). Kit reading,
protection, the gate, manifest assembly and the writer's self-scan are production code. Synthetic rows only.

Rule: no source cell value (any table and column: withheld tables, withheld columns, suppressed rows, raw forms of
transformed columns) of at least SCAN_MIN_LEN characters may appear in manifest text (outside `contract`; map keys
at any depth as well as values),
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
  a withheld note (paramName-shaped, one row) planted as a pets[].params map KEY (#149)
                                                     -> RELEASED at 7b21bc5 (keys unscanned); must refuse
  the writer's context has no `source` (#149, folded Standards finding)
                                                     -> at 7b21bc5 the source scan silently scanned nothing (refusal
                                                        only via other checks' not_run); must refuse with its own
                                                        content-free reason selfscan:source-missing
  a source value equal to a column name (one hand-made withheld note cell), planted as the whole fitFor[0].reason
  (#149 r2)                                          -> RELEASED at 19870a2 (header exemption at any path); must
                                                        refuse selfscan:manifest-value
  the same kit without the plant                     -> released (structural header paths stay exempt)
  honest hand release with #146's measured.kSets (a withheld column name holding a source value) (#149 r3)
                                                     -> REFUSED at 4b27878 (kSets name paths not listed); must release
  a withheld note in kSets withheld[0].reason or kSets.source       -> refuses (free text stays scanned)
  a source value equal to a column name as the whole kSets withheld[0].reason -> refuses
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


KEY_NOTE = "SyntheticWardRemarkStable"  # hand-made; satisfies the manifest paramName pattern (a valid map key)


def test_withheld_note_as_manifest_map_key_refuses(tmp_path, monkeypatch, capsys):
    """#149: a withheld note copied into a ``pets[].params`` KEY (not a value) refuses like a value would."""
    from pets_release.run import pipeline

    def edit(folder):
        coarse_qis(folder)
        p = folder / "clinical_notes.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[0, "note_text"] = KEY_NOTE
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    build_kit(tmp_path / "kit", edit)
    real = pipeline.build_narrative

    def leaky(**kw):
        nar = real(**kw)
        nar["pets"] = [dict(p, params={**p["params"], KEY_NOTE: 1}) if i == 0 else p
                       for i, p in enumerate(nar["pets"])]
        return nar

    monkeypatch.setattr(pipeline, "build_narrative", leaky)
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    from pets_release.cli import main

    out = tmp_path / "out" / "rel"
    code = main(["run", "--scenario", "HEALTH-S1", "--plan", "hand", "--kit", str(tmp_path / "kit"),
                 "--out", str(out), "--created", CREATED])
    capsys.readouterr()
    assert code == 1
    assert not out.exists()
    report = (out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8")
    reasons = json.loads(report)["reasons"]
    # the planted key passed every earlier check; only the manifest value scan (the registered check, read by
    # the writer's self-scan) refuses
    assert reasons == ["selfscan:check:producer.manifest-source-values:status:fail", "selfscan:manifest-value",
                       "selfscan:refused"]
    assert KEY_NOTE not in report


def test_missing_source_context_refuses_source_missing(tmp_path, monkeypatch, capsys):
    """#149 (folded Standards finding): a write whose context has no ``source`` cannot run the source-value scan.
    Unknown is a fail: the self-scan itself refuses with ``selfscan:source-missing`` (content-free), rather than
    silently scanning nothing and relying on another check's not_run."""
    from pets_release.run import pipeline

    build_kit(tmp_path / "kit", coarse_qis)
    real = pipeline.write_release

    def sourceless(cand, out, master, kit, *, context=None):
        return real(cand, out, master, kit, context={k: v for k, v in (context or {}).items() if k != "source"})

    monkeypatch.setattr(pipeline, "write_release", sourceless)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 1
    assert not out.exists()
    reasons = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))["reasons"]
    assert "selfscan:source-missing" in reasons


HEADER_VALUE = "chief_complaint"  # a source column NAME, written into one withheld note cell (hand-made)


def _kit_with_header_value(tmp_path):
    def edit(folder):
        coarse_qis(folder)
        p = folder / "clinical_notes.csv"
        df = pd.read_csv(p, dtype=str, keep_default_na=False, na_filter=False)
        df.loc[0, "note_text"] = HEADER_VALUE
        df.to_csv(p, index=False, encoding="utf-8", lineterminator="\n")

    return build_kit(tmp_path / "kit", edit)


def test_source_value_equal_to_header_in_free_text_refuses(tmp_path, monkeypatch, capsys):
    """#149 r2: the header exemption is bound to structural header paths. A source value that equals a column
    name, copied as the whole fitFor[0].reason, is scanned like any other text and refuses."""
    from pets_release.run import pipeline

    _kit_with_header_value(tmp_path)
    real = pipeline.build_narrative

    def leaky(**kw):
        nar = real(**kw)
        nar["fitFor"] = [dict(f, reason=HEADER_VALUE) if i == 0 else f for i, f in enumerate(nar["fitFor"])]
        return nar

    monkeypatch.setattr(pipeline, "build_narrative", leaky)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 1
    assert not out.exists()
    reasons = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))["reasons"]
    assert reasons == ["selfscan:check:producer.manifest-source-values:status:fail", "selfscan:manifest-value",
                       "selfscan:refused"]


def test_source_value_equal_to_header_honest_release_releases(tmp_path, monkeypatch, capsys):
    """Control for the row above: the same kit (a note cell equal to a column name) without the plant releases,
    so the column name at its structural paths (inventory, pets, contract, ...) stays exempt."""
    _kit_with_header_value(tmp_path)
    code, _ = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 0


def test_honest_release_with_k_sets_names_releases(tmp_path, monkeypatch, capsys):
    """#149 r3 (with #146): measured.kSets writes table/column names by construction (sets[].qi[], withheld[]);
    a withheld column whose NAME contains a source value must not refuse the honest release."""
    kit = build_kit(tmp_path / "kit", coarse_qis)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 0
    ks = json.loads((out / "privacy_manifest.json").read_text(encoding="utf-8"))["measured"]["kSets"]
    names = {w["column"] for w in ks["withheld"]} | {q["column"] for s in ks["sets"] for q in s.get("qi", [])}
    values = {v for t in ("clinical_notes", "ed_visits", "lab_results", "published_weekly_stats")
              for _, s in _read(kit, t).items() for v in s.unique() if len(v) >= SCAN_MIN_LEN}
    assert any(v in n for n in names for v in values)  # the kSets name exemption is really exercised


def _plant_k_sets(monkeypatch, field: str, value: str):
    from pets_release.run import pipeline

    real = pipeline.build_narrative

    def leaky(**kw):
        nar = real(**kw)
        ks = nar["measured"]["kSets"]
        if field == "withheld.reason":
            ks["withheld"][0]["reason"] = value
        else:
            ks[field] = value
        return nar

    monkeypatch.setattr(pipeline, "build_narrative", leaky)


@pytest.mark.parametrize("field", ["withheld.reason", "source"])
def test_withheld_note_in_k_sets_free_text_refuses(tmp_path, monkeypatch, capsys, field):
    """The kSets free text (withheld[].reason, source) stays scanned."""
    _kit_with_note(tmp_path)
    _plant_k_sets(monkeypatch, field, f"note {NOTE}")
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 1 and not out.exists()
    reasons = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))["reasons"]
    assert "selfscan:manifest-value" in reasons


def test_header_equal_source_value_as_k_sets_reason_refuses(tmp_path, monkeypatch, capsys):
    """A source value equal to a column name, as the whole kSets withheld[0].reason, is scanned (not exempt)."""
    _kit_with_header_value(tmp_path)
    _plant_k_sets(monkeypatch, "withheld.reason", HEADER_VALUE)
    code, out = _run(tmp_path, monkeypatch, None)
    capsys.readouterr()
    assert code == 1 and not out.exists()
    reasons = json.loads((out.parent / "rel.scoring" / "refusal_report.json").read_text(encoding="utf-8"))["reasons"]
    assert reasons == ["selfscan:check:producer.manifest-source-values:status:fail", "selfscan:manifest-value",
                       "selfscan:refused"]


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
