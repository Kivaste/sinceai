"""#139: red-team attacker (stronger than the spec-driven broker persona), measure-only.

Seam: the attacker CLI (``python -m pets_attacker`` -> ``cli.main``) on a hand-made synthetic kit and release.
Every row below is invented for this test (no kit rows).

Rule: besides the two personas, the attacker writes a ``red_team`` aggregate block with three attacks:
  cross_dataset        adversary records enriched from the kit's other-domain person tables by full name
                       (birth date -> age, sex, place), then scored as range_aware
  range_aware          Fellegi-Sunter scoring of interval overlaps (a disagreeing field lowers the score, it
                       does not veto); unique re-identification rate and 1-in-k guess success
  attribute_inference  per released sensitive attribute (field catalog role), majority vote over the best-scoring
                       rows for a target whose QIs the attacker knows, against the population base rate

Rows (trigger -> result):
  planted N1: news clip (date, place, name, no age); six same-day visits in that place, the target alone in its
      age band; a finance customer row with the same full name and a birth date
      -> broker persona misses (6 candidates); range_aware misses (1-in-6 guess); cross_dataset re-identifies
  planted N2: news clip with a wrong place and a right age -> broker misses (no candidate); range_aware and
      cross_dataset re-identify (the wrong place lowers every row equally)
  attribute inference over the 8 released visits -> icd10_primary 6/8 vs base rate 3/8
  an auxiliary table without its name column -> cross_dataset not evaluated with a reason; others measured
  no released sensitive attribute in the catalog -> attribute_inference not evaluated with a reason
  same inputs twice -> byte-identical output
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from pets_attacker.cli import main

ROOT = Path(__file__).resolve().parents[2]
RUNGS = {"ed_visits": {"arrival_ts": "ts.day", "age_band": "age.band10", "municipality": "keep",
                       "icd10_primary": "icd.3", "triage": "keep", "visit_id": "id.pseudonym"}}
NEWS_QIS = [
    {"kind": "time", "adversary": ["event_date", "published_date"], "protected": ["arrival_ts"], "window": [96, 24]},
    {"kind": "exact", "adversary": ["place"], "protected": ["municipality"]},
    {"kind": "age", "adversary": ["age_mentioned"], "protected": ["date_of_birth", "age", "age_band"], "tol": 3},
    {"kind": "sex", "adversary": ["sex_mentioned"], "protected": ["sex"]},
    {"kind": "name", "adversary": ["name_mentioned"], "protected": ["patient_name"]},
]
#            visit  person name              dob           sex  place    hour  band     icd    triage
VISITS = [("v1", "p1", "Aino Planted", "1990-05-01", "F", "Alpha", "08", "30-39", "A01", "3"),
          ("v2", "p2", "Bert Second", "1970-01-01", "M", "Alpha", "09", "50-59", "J10", "3"),
          ("v3", "p3", "Cara Third", "1970-02-01", "F", "Alpha", "10", "50-59", "J10", "3"),
          ("v4", "p4", "Dan Fourth", "1970-03-01", "M", "Alpha", "11", "50-59", "J10", "3"),
          ("v5", "p5", "Eva Fifth", "1970-04-01", "F", "Alpha", "12", "50-59", "K20", "3"),
          ("v6", "p6", "Finn Sixth", "1970-05-01", "M", "Alpha", "13", "50-59", "K21", "3"),
          ("v7", "p7", "Gus Seventh", "1980-06-01", "M", "Beta", "14", "40-49", "B02", "3"),
          ("v8", "p8", "Hilla Eighth", "1960-01-01", "F", "Beta", "15", "60-69", "C03", "3")]
CATALOG = ("dataset,table,column,privacy_role,data_kind,subtype\n"
           "health,ed_visits,visit_id,record_key,identifier,id\n"
           "health,ed_visits,municipality,quasi_identifier,categorical,place\n"
           "health,ed_visits,icd10_primary,sensitive_attribute,code,dx\n"
           "health,ed_visits,triage,sensitive_attribute,categorical,h\n")


def _csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")


def _kit(root: Path, *, catalog: str = CATALOG, finance_cols=("full_name", "birth_date", "city")) -> tuple:
    kit, rel = root / "kit", root / "rel"
    rel.mkdir(parents=True)
    cols = ["visit_id", "patient_hetu", "patient_name", "date_of_birth", "sex", "municipality", "arrival_ts",
            "icd10_primary", "triage"]
    orig = pd.DataFrame([(v, p, n, d, s, m, f"2025-03-10T{h}:15:00", i, t) for v, p, n, d, s, m, h, _, i, t in VISITS],
                        columns=cols)
    _csv(orig, kit / "data/health/ed_visits.csv")
    prot = pd.DataFrame({"visit_id": [f"r{i}" for i in range(len(VISITS))], "arrival_ts": ["2025-03-10"] * len(VISITS),
                         "age_band": [r[7] for r in VISITS], "municipality": [r[5] for r in VISITS],
                         "icd10_primary": [r[8] for r in VISITS], "triage": [r[9] for r in VISITS]})
    _csv(prot, rel / "ed_visits.csv")
    _csv(pd.DataFrame({"protected_row": range(len(VISITS)), "original_record_id": [r[0] for r in VISITS]}),
         rel / "rowmap_ed_visits.csv")
    _csv(pd.DataFrame({"record_id": [r[0] for r in VISITS], "person_id": [r[1] for r in VISITS]}),
         kit / "truth/health__ed_visits.csv")
    news = pd.DataFrame({"adv_row_id": ["n1", "n2"], "published_date": ["2025-03-11", "2025-03-11"],
                         "event_date": ["2025-03-10", "2025-03-10"], "place": ["Alpha", "Gamma"],
                         "age_mentioned": ["", "44"], "sex_mentioned": ["", ""],
                         "name_mentioned": ["Aino Planted", ""]})
    _csv(news, kit / "adversary/news_clips_health.csv")
    _csv(pd.DataFrame({"adv_row_id": ["n1", "n2"], "person_id": ["p1", "p7"]}),
         kit / "truth/adversary__news_clips_health.csv")
    fin = pd.DataFrame({"customer_id": ["c1", "c2"], "full_name": ["Aino Planted", "Bert Second"],
                        "birth_date": ["1990-05-01", "1970-01-01"], "city": ["Alpha", "Alpha"],
                        "hetu": ["p1", "p2"]})  # national ID: the same person as the visits' patient_hetu
    _csv(fin[["customer_id", "hetu", *finance_cols]], kit / "data/finance/customers.csv")
    spec = {"attacks": [{"adversary": "news_clips_health", "dataset": "health", "table": "ed_visits",
                         "sensitive": "icd10_primary", "qis": NEWS_QIS}]}
    (kit / "metadata").mkdir(parents=True, exist_ok=True)
    (kit / "metadata/attack_specs.json").write_text(json.dumps(spec), encoding="utf-8")
    (kit / "metadata/field_catalog.csv").write_text(catalog, encoding="utf-8")
    rungs = root / "rungs.json"
    rungs.write_text(json.dumps(RUNGS), encoding="utf-8")
    return kit, rel, rungs


LAB_CATALOG = CATALOG + ("health,lab_results,lab_id,record_key,identifier,id\n"
                         "health,lab_results,visit_id,record_key,identifier,id\n"
                         "health,lab_results,value,sensitive_attribute,numerical,m\n")


def _with_lab(kit: Path, rel: Path, rungs: Path, *, link: bool = True) -> None:
    """Round 2 (Sol Spec): a released lab table joined to the visits by the visit pseudonym. Two lab rows per
    released visit: value "5" for the Alpha 50-59 group (r1-r5), "7" for the rest; r0 (v1) also has one "9"."""
    keys = [f"r{i}" for i in range(len(VISITS))]
    rows = [(k, "5" if 1 <= i <= 5 else "7") for i, k in enumerate(keys) for _ in range(2)] + [("r0", "9")]
    lab = pd.DataFrame({"lab_id": [f"l{i}" for i in range(len(rows))],
                        "visit_id": [k for k, _ in rows] if link else [f"x{i}" for i in range(len(rows))],
                        "value": [v for _, v in rows]})
    _csv(lab, rel / "lab_results.csv")
    r = json.loads(rungs.read_text(encoding="utf-8"))
    r["lab_results"] = {"lab_id": "id.pseudonym", "visit_id": "id.pseudonym" if link else "keep",
                        "value": "num.exact"}
    rungs.write_text(json.dumps(r), encoding="utf-8")
    (kit / "metadata/field_catalog.csv").write_text(LAB_CATALOG, encoding="utf-8")


def _run(root: Path, lab: bool | str = False, **kw) -> dict:
    kit, rel, rungs = _kit(root, **kw)
    if lab:
        _with_lab(kit, rel, rungs, link=lab != "unlinked")
    out = root / "attack.json"
    assert main(["--kit", str(kit), "--release", str(rel), "--label", "t", "--out", str(out),
                 "--rungs", str(rungs)]) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_cross_dataset_reidentifies_the_planted_target_the_public_broker_misses(tmp_path):
    res = _run(tmp_path)
    broker = res["broker"]["news_clips_health"]
    assert broker["n_targets"] == 2 and broker["reidentification_rate"] == 0.0  # the spec-driven attacker misses
    cross = res["red_team"]["cross_dataset"]
    assert cross["evaluated"] is True and cross["n_targets"] == 2
    assert cross["reidentification_rate"] == 1.0 and cross["guess_rate"] == 1.0
    assert cross["n_enriched"] == 1


def test_range_aware_scoring_tolerates_a_wrong_field_and_reports_one_in_k_guess_success(tmp_path):
    """N2 states a wrong place: the hard filter has no candidate, the scoring still singles out the right visit.
    N1 (no age, no enrichment) ties six same-day visits in its place: 1-in-6 guess success."""
    rng = _run(tmp_path)["red_team"]["range_aware"]
    assert rng["evaluated"] is True and rng["n_targets"] == 2
    assert rng["reidentification_rate"] == 0.5 and rng["n_unique_claims"] == 1
    assert rng["guess_rate"] == round((1 / 6 + 1) / 2, 4)
    assert rng["median_top_set"] == 3.5


def test_attribute_inference_per_released_sensitive_attribute_against_the_base_rate(tmp_path):
    """An attacker knowing each released visit's exact QIs: icd10_primary by majority over the best rows (the
    50-59 Alpha group votes J10, wrong for two): right for v1, v2-v4, v7 and v8 = 6 of 8, against 3 of 8 for
    always guessing the commonest code."""
    ai = _run(tmp_path)["red_team"]["attribute_inference"]
    assert ai["evaluated"] is True and ai["reason"] is None
    assert sorted(ai["columns"]) == ["icd10_primary", "triage"]
    icd = ai["columns"]["icd10_primary"]
    assert icd == {"evaluated": True, "reason": None, "n_targets": 8, "inference_rate": 0.75, "baseline_rate": 0.375}
    assert ai["columns"]["triage"]["inference_rate"] == 1.0 and ai["columns"]["triage"]["baseline_rate"] == 1.0


def test_attribute_inference_is_not_measured_without_a_released_sensitive_attribute(tmp_path):
    no_sensitive = CATALOG.replace("sensitive_attribute", "other")
    ai = _run(tmp_path, catalog=no_sensitive)["red_team"]["attribute_inference"]
    assert ai == {"evaluated": False, "reason": "no-sensitive-released", "columns": {}}


def test_a_malformed_auxiliary_table_makes_cross_dataset_not_measured_never_zero(tmp_path):
    res = _run(tmp_path, finance_cols=("birth_date", "city"))  # no name column
    cross = res["red_team"]["cross_dataset"]
    assert cross["evaluated"] is False and cross["reason"] == "aux-table-malformed"
    assert cross["reidentification_rate"] is None and cross["guess_rate"] is None
    assert res["red_team"]["range_aware"]["evaluated"] is True


def test_without_any_auxiliary_table_cross_dataset_is_not_measured(tmp_path):
    kit, rel, rungs = _kit(tmp_path)
    (kit / "data/finance/customers.csv").unlink()
    out = tmp_path / "attack.json"
    assert main(["--kit", str(kit), "--release", str(rel), "--label", "t", "--out", str(out),
                 "--rungs", str(rungs)]) == 0
    cross = json.loads(out.read_text(encoding="utf-8"))["red_team"]["cross_dataset"]
    assert cross["evaluated"] is False and cross["reason"] == "no-aux-table" and cross["reidentification_rate"] is None


def test_real_cli_is_deterministic_and_content_free(tmp_path):
    """Seam: the real ``python -m pets_attacker`` child, twice on the same inputs: byte-identical output that
    holds no name, place, code or id from the inputs."""
    kit, rel, rungs = _kit(tmp_path)
    outs = []
    for i in range(2):
        out = tmp_path / f"attack{i}.json"
        env = {"PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
               "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
        p = subprocess.run([sys.executable, "-m", "pets_attacker", "--kit", str(kit), "--release", str(rel),
                            "--label", "t", "--out", str(out), "--rungs", str(rungs)],
                           env=env, capture_output=True, text=True, timeout=300, check=False)
        assert p.returncode == 0, p.stderr[-500:]
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
    text = outs[0].decode("utf-8")
    assert '"red_team"' in text
    for leaked in ("Aino", "Planted", "Alpha", "Beta", "Gamma", "A01", "J10", "1990", "n1", "p1", "v1", "r0"):
        assert leaked not in text, leaked


def test_attribute_inference_covers_a_sensitive_column_of_every_released_table(tmp_path):
    """Round 2 (Sol Spec HIGH). Lab targets (17 released lab rows) inherit their visit's QIs through the shared
    visit pseudonym; the vote runs over the lab rows of the best-scoring visits. Right: r0's 2 of 3, all 10 of
    r1-r5, 2 of r6, 2 of r7 = 16/17; base rate (always "5") = 10/17."""
    ai = _run(tmp_path, lab=True)["red_team"]["attribute_inference"]
    assert sorted(ai["columns"]) == ["icd10_primary", "lab_results.value", "triage"]
    assert ai["columns"]["lab_results.value"] == {"evaluated": True, "reason": None, "n_targets": 17,
                                                  "inference_rate": round(16 / 17, 4),
                                                  "baseline_rate": round(10 / 17, 4)}
    assert ai["columns"]["icd10_primary"]["inference_rate"] == 0.75  # unchanged by the extra table


def test_a_released_table_without_a_pseudonym_link_is_not_measured_with_its_reason(tmp_path):
    ai = _run(tmp_path, lab="unlinked")["red_team"]["attribute_inference"]
    lab = ai["columns"]["lab_results.value"]
    assert lab["evaluated"] is False and lab["reason"] == "no-link-to-target-table" and lab["inference_rate"] is None


def test_release_join_links_released_rows_to_the_kits_person_register_on_the_released_qis(tmp_path):
    """Round 2 (Spec r1, item 2). The finance customers (national ID, birth date, city) join the RELEASED visits on
    the released age band and municipality: p1 (35, Alpha) is alone in 30-39 Alpha -> re-identified; p2 (55,
    Alpha) ties five visits -> 1-in-5. Unique 1/2, guess (1 + 1/5)/2. Through the visit pseudonym, p1's 3 lab rows
    are re-identified, p2's 2 are not: 3/5 lab rows."""
    rj = _run(tmp_path, lab=True)["red_team"]["release_join"]
    assert rj["evaluated"] is True and rj["n_targets"] == 2 and rj["n_register_sources"] == 1
    assert rj["reidentification_rate"] == 0.5 and rj["guess_rate"] == 0.6
    assert rj["linked_table"] == "lab_results" and rj["linked_n_targets"] == 5 and rj["linked_reidentification_rate"] == 0.6


def test_release_join_without_a_person_register_is_not_measured(tmp_path):
    kit, rel, rungs = _kit(tmp_path)
    (kit / "data/finance/customers.csv").unlink()
    out = tmp_path / "attack.json"
    assert main(["--kit", str(kit), "--release", str(rel), "--label", "t", "--out", str(out),
                 "--rungs", str(rungs)]) == 0
    rj = json.loads(out.read_text(encoding="utf-8"))["red_team"]["release_join"]
    assert rj["evaluated"] is False and rj["reason"] == "no-register" and rj["reidentification_rate"] is None


def test_planted_target_is_missed_by_the_kits_public_pets_eval_attacker_and_hit_by_the_red_team(tmp_path):
    """r3 (Spec, acceptance): the kit's own public attacker (the unmodified ``pets_eval scorecard`` child, as the
    measurer runs it) on the same synthetic kit and release misses both planted targets; the red team's
    cross-dataset attack re-identifies both. Seams: the pets-eval CLI and the attacker CLI (real children)."""
    import shutil

    kit, rel, rungs = _kit(tmp_path)
    (kit / "metadata/scenarios.json").write_text(
        json.dumps([{"id": "RT-S1", "dataset": "health", "utility_requirements": []}]), encoding="utf-8")
    scoring = tmp_path / "scoring"  # pets-eval: row maps outside the release
    scoring.mkdir()
    shutil.move(str(rel / "rowmap_ed_visits.csv"), scoring / "rowmap_ed_visits.csv")
    env = {"PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
           "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    pe_out = tmp_path / "pets-eval"
    p = subprocess.run([sys.executable, "-m", "pets_eval", "scorecard", "--original", str(kit / "data/health"),
                        "--protected", str(rel), "--scenario", "RT-S1", "--root", str(kit), "--out", str(pe_out),
                        "--rowmap", f"ed_visits={scoring / 'rowmap_ed_visits.csv'}"],
                       env=env, capture_output=True, text=True, timeout=600, check=False)
    assert p.returncode == 0, p.stderr[-500:]  # pets_eval missing or failing is a fail, never a skip
    public = json.loads((pe_out / "scorecard.json").read_text(encoding="utf-8"))["tables"]["ed_visits"]["linkage"]
    news = public["news_clips_health"]
    assert news["n_targets_in_data"] == 2 and news["n_unique_claims"] == 0 and news["reidentification_rate"] == 0.0
    out = tmp_path / "attack.json"
    p = subprocess.run([sys.executable, "-m", "pets_attacker", "--kit", str(kit), "--release", str(rel), "--label", "t",
                        "--out", str(out), "--rungs", str(rungs), "--scoring-dir", str(scoring)],
                       env=env, capture_output=True, text=True, timeout=600, check=False)
    assert p.returncode == 0, p.stderr[-500:]
    cross = json.loads(out.read_text(encoding="utf-8"))["red_team"]["cross_dataset"]
    assert cross["n_targets"] == 2 and cross["reidentification_rate"] == 1.0
