"""The out-of-process scorecard, through the real pets-eval CLI, on a tiny synthetic kit."""

import json

import pandas as pd
import pytest

from pets_release.kiteval import (
    Lineage,
    RowMapRejected,
    ScorecardRejected,
    run_scorecard,
)

ROWS = [("c1", "refund", "300"), ("c2", "refund", "500"), ("c3", "billing", "200"), ("c4", "billing", "400")]


LINEAGE = Lineage(final=tuple(r[0] for r in ROWS), suppressed=frozenset())


def _write(path, rows, cols=("conversation_id", "intent", "handle_time_s")):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=list(cols), dtype=str).to_csv(path, index=False)


@pytest.fixture
def kit(tmp_path):
    root = tmp_path / "kit"
    (root / "metadata").mkdir(parents=True)
    (root / "metadata" / "scenarios.json").write_text(
        json.dumps([{"id": "TEST-S1", "dataset": "customer_service", "utility_requirements": ["CS-U4"]}]),
        encoding="utf-8",
    )
    (root / "metadata" / "field_catalog.csv").write_text(
        "dataset,table,column,privacy_role,data_kind,subtype\n"
        "customer_service,conversations,conversation_id,record_key,identifier,id\n",
        encoding="utf-8",
    )
    _write(root / "data" / "customer_service" / "conversations.csv", ROWS)
    return root


@pytest.fixture
def release(tmp_path):
    out = tmp_path / "release" / "customer_service"
    _write(out / "conversations.csv", ROWS)
    rm = tmp_path / "scoring" / "rowmap_conversations.csv"
    rm.parent.mkdir(parents=True)
    pd.DataFrame({"protected_row": range(4), "original_record_id": [r[0] for r in ROWS]}).to_csv(rm, index=False)
    return out, {"conversations": rm}, tmp_path / "scoring" / "kit-out"


def _run(kit, release, **over):
    prot, rms, out = release
    args = {"scenario": "TEST-S1", "root": kit, "rowmaps": rms, "out_dir": out,
            "lineage": {"conversations": LINEAGE}, **over}
    return run_scorecard(kit / "data" / "customer_service", prot, **args)


def test_real_scorecard_returns_allowlisted_summary_and_keeps_raw_output(kit, release):
    summary = _run(kit, release)
    assert summary["scenario"] == "TEST-S1"
    assert summary["tasks"] == [{"id": "CS-U4", "score": 1.0, "required": True, "status": "ok"}]
    assert set(summary) == {"scenario", "dataset", "privacy", "utility", "composite", "tasks", "risks", "tables",
                          "not_applicable"}
    out = release[2]
    assert (out / "scorecard.json").exists()
    assert not list(release[0].glob("scorecard.*"))  # nothing written into the release folder


def test_wrong_scenario_id_is_rejected_before_running(kit, release):
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release, scenario="CS-S1")
    assert caught.value.reason == "scenario"
    assert not release[2].exists()


def test_protected_table_without_row_map_is_rejected(kit, release):
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release, rowmaps={})
    assert caught.value.reason == "missing_map"


def test_row_map_missing_a_row_is_rejected(kit, release):
    rms = release[1]
    pd.DataFrame({"protected_row": [0, 1, 2], "original_record_id": ["c1", "c2", "c3"]}).to_csv(
        rms["conversations"], index=False)
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "missing_row"


def test_row_map_with_foreign_key_is_rejected(kit, release):
    rms = release[1]
    pd.DataFrame({"protected_row": range(4), "original_record_id": ["c1", "c2", "c3", "zz"]}).to_csv(
        rms["conversations"], index=False)
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "unknown_source_key"


def test_out_dir_inside_release_is_rejected(kit, release):
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release, out_dir=release[0] / "scoring")
    assert caught.value.reason == "out_dir_inside_release"


def test_planted_scorecard_does_not_stand_in_for_a_run_that_wrote_nothing(kit, release, monkeypatch):
    import subprocess

    out = release[2]
    out.mkdir(parents=True)
    (out / "scorecard.json").write_text(
        json.dumps({"summary": {"privacy": 1, "utility": 1, "composite": 1}}), encoding="utf-8")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=b"", stderr=b""))
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "structure"


def test_evaluator_exit_code_nonzero_is_a_fail(kit, release, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout=b"", stderr=b""))
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "evaluator_failed"


def test_lineage_is_required_for_every_protected_table(kit, release):
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release, lineage={})
    assert caught.value.reason == "missing_lineage"


def test_row_map_that_disagrees_with_writer_lineage_is_rejected(kit, release):
    rms = release[1]
    pd.DataFrame({"protected_row": range(4), "original_record_id": ["c2", "c1", "c3", "c4"]}).to_csv(
        rms["conversations"], index=False)
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "lineage_mismatch"


def test_relative_paths_work(kit, release, tmp_path, monkeypatch):
    import os

    prot, rms, out = release
    monkeypatch.chdir(tmp_path)
    rel = lambda p: os.path.relpath(p, tmp_path)
    summary = run_scorecard(
        rel(kit / "data" / "customer_service"), rel(prot), scenario="TEST-S1", root=rel(kit),
        rowmaps={k: rel(v) for k, v in rms.items()}, out_dir=rel(out), lineage={"conversations": LINEAGE})
    assert summary["tasks"][0]["status"] == "ok"



def test_row_map_inside_the_release_folder_is_rejected(kit, release):
    import shutil

    prot, rms, _out = release
    inside = prot / "rowmap_conversations.csv"
    shutil.copy(rms["conversations"], inside)
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release, rowmaps={"conversations": inside})
    assert caught.value.reason == "rowmap_in_release"


def test_required_result_sections_come_from_the_kit_for_this_scenario(kit, release):
    # the synthetic kit has no truth/spans, so no linkage or free-text section is required of the report
    summary = _run(kit, release)
    # no catalogued quasi-identifier in the synthetic kit: recorded, with its code, not hidden
    assert summary["not_applicable"] == [
        {"table": "conversations", "section": "k_anonymity", "key": "", "code": "no_quasi_identifier"}]



def test_planted_row_map_in_the_release_is_refused_even_if_not_passed(kit, release):
    prot = release[0]
    (prot / "rowmap_conversations.csv").write_text("protected_row,original_record_id\n0,c1\n", encoding="utf-8")
    with pytest.raises(RowMapRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "rowmap_in_release"


@pytest.mark.parametrize("name", ["notes.txt", "scorecard.json", "extra.csv"])
def test_any_file_beyond_the_tables_and_manifest_is_refused(kit, release, name):
    (release[0] / name).write_text("x", encoding="utf-8")
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release)
    assert caught.value.reason in {"release_extra_file", "unknown_table"}


def test_subfolder_in_the_release_is_refused(kit, release):
    (release[0] / "sub").mkdir()
    with pytest.raises(ScorecardRejected) as caught:
        _run(kit, release)
    assert caught.value.reason == "release_extra_file"


def test_manifest_alone_is_allowed_next_to_the_tables(kit, release):
    (release[0] / "privacy_manifest.json").write_text("{}", encoding="utf-8")
    assert _run(kit, release)["tasks"][0]["status"] == "ok"


@pytest.mark.parametrize("name", ["_private.csv", "_.csv", "rowmap_other.csv", "Extra.CSV", "x.parquet"])
def test_underscore_and_other_files_the_evaluator_ignores_are_still_refused(kit, release, name):
    (release[0] / name).write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises((ScorecardRejected, RowMapRejected)):
        _run(kit, release)
