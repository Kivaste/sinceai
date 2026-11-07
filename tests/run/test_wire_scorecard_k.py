"""Must-fixes #110 and #113, through the measure CLI (``python -m pets_release.measure.wire`` -> ``wire.main``).

#110 rule: the scorecard's k evaluation is never skipped silently. Which released tables must carry a k result
(denominator + "records with k<5" component) is derived from the kit's catalog and the release's columns; the
"no catalogued quasi-identifier kept" note is accepted only when that derivation says no QI was kept.
Seam: measure CLI with the real measurer and the real pets-eval child on the synthetic minikit; the child's
report is rewritten after it ran, the way a silent skip would look.

Rows (trigger -> result):
  untampered report                                      -> exit 0, released (benign note on QI-less tables)
  k result replaced by the "no QI kept" note + k<5 dropped -> exit 2 ScorecardRejected, nothing released
  k denominator kept, k<5 component dropped               -> exit 2, nothing released
  k computed on a QI set other than the catalog's         -> exit 2, nothing released
  k claimed for a table that keeps no catalogued QI       -> exit 2, nothing released

#113 rule: measure.wire takes row maps by identity (the stems in the run's own lineage), never by file presence.
Seam: measure CLI; the measurer is stubbed (as in test_wire.py) so the selector itself is observed.
  planted extra rowmap_*.csv in the scratch scoring folder -> exit 2 RunError, nothing released
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from run_helpers import TEST_KEY, build_kit, coarse_qis, run_args

from pets_release.measure import wire
from pets_release.run import pipeline

QI = "municipality"  # the only catalogued quasi-identifier of the synthetic catalog below (ed_visits)
CATALOG = ("dataset,table,column,privacy_role,data_kind,subtype\n"
           "health,ed_visits,visit_id,record_key,identifier,id\n"
           f"health,ed_visits,{QI},quasi_identifier,categorical,place\n"
           "health,lab_results,lab_id,record_key,identifier,id\n"
           "health,clinical_notes,note_id,record_key,identifier,id\n"
           "health,published_weekly_stats,stat_id,record_key,identifier,id\n")
K_RISK = "records with k<5"
NO_QI_NOTE = "no catalogued quasi-identifier kept"


def _bench() -> dict:
    b = {"privacy": 0.5, "utility": 0.5, "composite": 0.5, "worst_reid": 0.5, "residual_identifiers": 0.0,
         "utility_tasks": {"H-U2": 0.5}, "utility_by_scenario": {"HEALTH-S1": 0.5}, "runtime_s": 1.0}
    return {"generated": "fixture", "baselines": {f"{p}_health": dict(b) for p in ("B0", "B2", "B2K")}}


@pytest.fixture
def measured_kit(tmp_path, monkeypatch):
    """The run minikit plus what the real measurer needs: a hand-made catalog and invented baselines."""
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit = build_kit(tmp_path / "kit", edit=coarse_qis)
    (kit / "metadata" / "field_catalog.csv").write_text(CATALOG, encoding="utf-8")
    (kit / "results").mkdir()
    (kit / "results" / "benchmark.json").write_text(json.dumps(_bench()), encoding="utf-8")
    return kit, tmp_path / "rel"


def _rewrite_after_report(monkeypatch, mutate):
    """Run the real pets-eval child; then rewrite the report it wrote for the release ("after") pass."""
    real = subprocess.run

    def run(cmd, *a, **k):
        proc = real(cmd, *a, **k)
        if isinstance(cmd, list) and "--protected" in cmd and Path(cmd[cmd.index("--protected") + 1]).name == "pass1":
            out = Path(cmd[cmd.index("--out") + 1]) / "scorecard.json"
            report = json.loads(out.read_text(encoding="utf-8"))
            mutate(report)
            out.write_text(json.dumps(report), encoding="utf-8")
        return proc

    monkeypatch.setattr(subprocess, "run", run)


def _drop_k_component(report, table="ed_visits"):
    report["tables"][table]["risks"].pop(K_RISK)
    report["risk_components"].pop(f"{table}: {K_RISK}")


def _note_instead_of_k(report):
    report["tables"]["ed_visits"]["k_anonymity"] = {"note": NO_QI_NOTE}
    _drop_k_component(report)


def _other_qis(report):
    report["tables"]["ed_visits"]["k_anonymity"]["qis"] = ["sex"]


def _k_without_qi(report):
    tr = report["tables"]["lab_results"]  # no catalogued QI: the kit writes the note, never a k result
    tr["k_anonymity"] = {"qis": ["test_code"], "n": tr["rows_protected"], "min_k": 1,
                         "share_below": {"k<2": 0.0, "k<5": 0.0, "k<10": 0.0}}
    tr["risks"][K_RISK] = 0.0
    report["risk_components"][f"lab_results: {K_RISK}"] = 0.0


def test_untampered_report_releases_through_the_measure_cli(measured_kit):
    kit, out = measured_kit
    assert wire.main(run_args(kit, out)[1:]) == 0
    assert any(out.glob("*.csv"))


@pytest.mark.parametrize("mutate", [_note_instead_of_k, _drop_k_component, _other_qis, _k_without_qi],
                         ids=["note_instead_of_k", "k_component_dropped", "other_qis", "k_without_qi"])
def test_skipped_or_contradicting_k_evaluation_fails_the_measure_cli(measured_kit, monkeypatch, capsys, mutate):
    kit, out = measured_kit
    _rewrite_after_report(monkeypatch, mutate)
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "ScorecardRejected" in capsys.readouterr().err
    assert not out.exists()


# ---- #113: row maps by identity, not presence ---------------------------------------------------------

STUB_BLOCK = {k: {"status": "not_measured", "reason": "stub"} for k in ("utility", "privacy", "baselines", "search",
                                                                       "redaction")}


@pytest.mark.parametrize("planted", ["rowmap_ghost.csv", "rowmap_clinical_notes.csv", "ROWMAP_Ghost.csv"])
def test_planted_row_map_in_the_scoring_folder_is_refused_by_the_measure_cli(tmp_path, monkeypatch, capsys, planted):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    kit, out = build_kit(tmp_path / "kit", edit=coarse_qis), tmp_path / "rel"
    monkeypatch.setattr(wire, "measure", lambda *a, **k: dict(STUB_BLOCK))
    monkeypatch.setattr(wire, "person_k_components", lambda *a, **k: [])
    monkeypatch.setattr(wire, "_person_k_from_release", lambda **k: None)
    real = pipeline.run_release

    def run_release(**kw):
        res = real(**kw)
        if res.status == "released" and Path(kw["out"]).name == "pass1":  # plant next to the run's own maps
            (res.scoring / planted).write_text("protected_row,original_record_id\n0,x\n", encoding="utf-8")
        return res

    monkeypatch.setattr(pipeline, "run_release", run_release)
    assert wire.main(run_args(kit, out)[1:]) == 2
    assert "row map" in capsys.readouterr().err
    assert not out.exists()
