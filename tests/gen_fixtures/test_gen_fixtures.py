"""Seams for the synthetic mini-kit generator.

1. generate(dest) writes health and customer_service tables with the kit's column names.
   Catches a missing table or a renamed column. Misses whether a task can score the values.
2. Two runs are byte-identical, and the committed fixture matches a fresh run.
   Catches unstable order or clock input. Misses a generator that is stable but empty.
3. Train coverage and joined visit/lab rows per diagnosis group.
   Catches an undersized fixture. Misses a shape the task still rejects.
4. pets-eval required tasks score original versus itself.
   Catches not-answerable and errored tasks. Misses privacy properties.
5. A planted kit path is ignored.
   Catches a generator that copies an external file. Misses a value typed in by hand.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_fixtures.py"
COMMITTED = ROOT / "tests" / "fixtures" / "minikit"
PYTHON = Path(r"C:\Users\kivas\AI\sinceai-hackaton\.venv\Scripts\python.exe")

HEALTH_COLUMNS = {
    "ed_visits": [
        "visit_id", "patient_hetu", "patient_name", "date_of_birth", "sex", "phone",
        "home_address", "postcode", "municipality", "arrival_ts", "arrival_mode",
        "ambulance_unit", "triage", "chief_complaint", "icd10_primary", "icd10_secondary",
        "systolic_bp", "diastolic_bp", "heart_rate", "resp_rate", "temp_c", "spo2",
        "pain_nrs", "attending_physician_id", "attending_physician_name", "discharge_ts",
        "los_minutes", "disposition", "readmit_30d",
    ],
    "lab_results": [
        "lab_id", "visit_id", "test_code", "test_name", "value", "unit", "ref_range",
        "abnormal_flag", "sampled_ts",
    ],
    "clinical_notes": [
        "note_id", "visit_id", "note_type", "author_staff_id", "author_name",
        "written_ts", "language", "note_text",
    ],
    "published_weekly_stats": [
        "stat_id", "week", "municipality", "age_band", "sex", "diagnosis_group", "visits",
    ],
}

CS_COLUMNS = {
    "customers": [
        "customer_id", "customer_number", "full_name", "hetu", "street_address",
        "postcode", "city", "email", "phone", "preferred_language", "customer_since",
        "products", "contract_number", "payment_method", "iban", "marketing_consent",
        "payment_default_flag", "accessibility_needs",
    ],
    "conversations": [
        "conversation_id", "customer_id", "agent_id", "agent_name", "channel",
        "language", "started_ts", "intent", "sentiment", "csat", "resolved",
        "handle_time_s", "n_turns", "split", "agent_note",
    ],
    "turns": ["turn_id", "conversation_id", "seq", "speaker", "ts", "text"],
}

REQUIRED = {
    "health": {
        "id": "HEALTH-S1",
        "utility_requirements": ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"],
    },
    "customer_service": {
        "id": "CS-S1",
        "utility_requirements": ["CS-U1", "CS-U3", "CS-U4", "CS-U5"],
    },
}

SENTINEL = "PLANTED-KIT-SENTINEL-zz9"


def _load():
    assert SCRIPT.is_file(), f"missing generator: {SCRIPT}"
    spec = importlib.util.spec_from_file_location("gen_fixtures", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _csv_bytes(folder: Path) -> dict[str, bytes]:
    files = sorted(folder.rglob("*.csv"))
    assert files, f"no csv files under {folder}"
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in files}


def _lines(blob: bytes) -> list[str]:
    return blob.decode("utf-8").splitlines()


@pytest.fixture
def gen():
    return _load()


def test_generate_writes_kit_tables_and_columns(tmp_path, gen):
    dest = tmp_path / "kit"
    gen.generate(dest)
    for domain, columns in (("health", HEALTH_COLUMNS), ("customer_service", CS_COLUMNS)):
        for table, expected in columns.items():
            path = dest / domain / f"{table}.csv"
            assert path.is_file(), f"missing {domain}/{table}.csv"
            header = path.read_text(encoding="utf-8").splitlines()[0]
            assert header.split(",") == expected


def test_two_runs_are_byte_identical(tmp_path, gen):
    first = tmp_path / "first"
    second = tmp_path / "second"
    gen.generate(first)
    gen.generate(second)
    assert _csv_bytes(first) == _csv_bytes(second)


def test_committed_fixture_matches_generator(tmp_path, gen):
    fresh = tmp_path / "fresh"
    gen.generate(fresh)
    got = _csv_bytes(fresh)
    committed = _csv_bytes(COMMITTED)
    assert set(got) == set(committed)
    for name in sorted(got):
        assert _lines(got[name]) == _lines(committed[name]), name


def test_script_entrypoint_writes_the_same_fixture(tmp_path, gen):
    via_import = tmp_path / "import"
    via_cli = tmp_path / "cli"
    gen.generate(via_import)
    env = {
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TZ": "UTC",
        "PATH": "",
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
    }
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "--out", str(via_cli)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert _csv_bytes(via_import) == _csv_bytes(via_cli)


def test_train_split_has_every_intent_class(tmp_path, gen):
    gen.generate(tmp_path / "kit")
    conv = pd.read_csv(tmp_path / "kit" / "customer_service" / "conversations.csv", dtype=str)
    train = conv[conv["split"] == "train"]
    assert len(train) >= 50
    assert train["intent"].nunique() == 15
    assert set(train["intent"]) == set(gen.INTENT_CLASSES)
    assert len(gen.INTENT_CLASSES) == 15


def test_each_scored_diagnosis_group_has_thirty_joined_rows(tmp_path, gen):
    gen.generate(tmp_path / "kit")
    visits = pd.read_csv(tmp_path / "kit" / "health" / "ed_visits.csv", dtype=str)
    labs = pd.read_csv(tmp_path / "kit" / "health" / "lab_results.csv", dtype=str)
    from pets_eval.utility.health import GROUP_NAMES, diagnosis_group

    kept = visits[visits["disposition"].fillna("") != "cancelled_duplicate"]
    crp = labs.loc[labs["test_code"] == "P-CRP", ["visit_id", "value"]]
    joined = kept.merge(crp, on="visit_id", how="inner")
    temp = pd.to_numeric(joined["temp_c"], errors="coerce")
    crp_value = pd.to_numeric(joined["value"], errors="coerce")
    joined = joined[(temp > 34) & (temp < 42.5) & crp_value.notna()]
    groups = diagnosis_group(joined["icd10_primary"])
    counts = groups.value_counts(dropna=True)
    missing = sorted(GROUP_NAMES - set(counts.index))
    assert missing == []
    short = sorted(g for g, n in counts.items() if n < 30)
    assert short == []


def test_required_tasks_score_original_against_itself(tmp_path, gen):
    gen.generate(tmp_path / "kit")
    from pets_eval.io import load_tables
    from pets_eval.scorecard import run_utility

    for domain, scenario in REQUIRED.items():
        tables = load_tables(tmp_path / "kit" / domain)
        scored = run_utility(domain, tables, tables, scenario)
        by_id = {row["id"]: row for row in scored}
        for task_id in scenario["utility_requirements"]:
            row = by_id[task_id]
            assert row["metric"] not in {"not answerable", "error"}, (task_id, row["metric"], row.get("detail"))
            assert row["score"] is not None, task_id
            assert row["score"] >= 0.99, (task_id, row["score"], row["metric"])


def test_generator_ignores_a_planted_kit(tmp_path, gen, monkeypatch):
    planted = tmp_path / "planted-kit" / "data" / "health"
    planted.mkdir(parents=True)
    (planted / "ed_visits.csv").write_text(f"visit_id\n{SENTINEL}\n", encoding="utf-8")
    monkeypatch.setenv("PETS_KIT", str(tmp_path / "planted-kit"))
    monkeypatch.setenv("PETS_ROOT", str(tmp_path / "planted-kit"))
    dest = tmp_path / "out"
    gen.generate(dest)
    blob = "\n".join(p.read_text(encoding="utf-8") for p in dest.rglob("*.csv"))
    assert SENTINEL not in blob
    source = SCRIPT.read_text(encoding="utf-8")
    assert "read_csv" not in source
    assert "Briefs" not in source
    assert "TRUSTED_PETS" not in source


def test_leading_zero_postcode_is_text(tmp_path, gen):
    gen.generate(tmp_path / "kit")
    raw = (tmp_path / "kit" / "health" / "ed_visits.csv").read_text(encoding="utf-8")
    zero_codes = [code for code in gen.POSTCODES if str(code).startswith("0")]
    assert zero_codes
    assert zero_codes[0] in raw
    visits = pd.read_csv(tmp_path / "kit" / "health" / "ed_visits.csv", dtype=str)
    assert visits["visit_id"].str.match(r"ED25-\d{6}$").all()


def test_committed_fixture_bytes_are_protected_from_line_ending_conversion():
    attrs = (COMMITTED / ".gitattributes").read_text(encoding="utf-8")
    assert "-text" in attrs.split()
    assert all(b"\r" not in blob for blob in _csv_bytes(COMMITTED).values())


def test_identity_codes_use_the_reserved_synthetic_range(tmp_path, gen):
    gen.generate(tmp_path / "kit")
    visits = pd.read_csv(tmp_path / "kit" / "health" / "ed_visits.csv", dtype=str)
    individual = visits["patient_hetu"].str[7:10]
    assert individual.str.match(r"9\d\d$").all()
