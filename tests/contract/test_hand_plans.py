"""Hand-plan contracts: withheld absence, derived age_band, forms, stable digest."""

from __future__ import annotations

from pets_release.contract import digest, generate
from pets_release.contract.forms import MONTH_HOUR_FORM, TOKEN_FORM
from pets_release.contract.hand_plans import cs_plan, health_plan, render

_HEALTH_COLUMNS = {
    "ed_visits": {
        "visit_id", "patient_hetu", "patient_name", "date_of_birth", "sex", "phone", "home_address",
        "postcode", "municipality", "arrival_ts", "arrival_mode", "ambulance_unit", "triage",
        "chief_complaint", "icd10_primary", "icd10_secondary", "systolic_bp", "diastolic_bp",
        "heart_rate", "resp_rate", "temp_c", "spo2", "pain_nrs", "attending_physician_id",
        "attending_physician_name", "discharge_ts", "los_minutes", "disposition", "readmit_30d",
    },
    "lab_results": {
        "lab_id", "visit_id", "test_code", "test_name", "value", "unit", "ref_range",
        "abnormal_flag", "sampled_ts",
    },
    "clinical_notes": {
        "note_id", "visit_id", "note_type", "author_staff_id", "author_name", "written_ts",
        "language", "note_text",
    },
    "published_weekly_stats": {
        "stat_id", "week", "municipality", "age_band", "sex", "diagnosis_group", "visits",
    },
}

_CS_COLUMNS = {
    "conversations": {
        "conversation_id", "customer_id", "agent_id", "agent_name", "channel", "language",
        "started_ts", "intent", "sentiment", "csat", "resolved", "handle_time_s", "n_turns",
        "split", "agent_note",
    },
    "customers": {
        "customer_id", "customer_number", "full_name", "hetu", "street_address", "postcode", "city",
        "email", "phone", "preferred_language", "customer_since", "products", "contract_number",
        "payment_method", "iban", "marketing_consent", "payment_default_flag", "accessibility_needs",
    },
    "turns": {"turn_id", "conversation_id", "seq", "speaker", "ts", "text"},
}


def _covered(policy: dict, plan: list[dict], expected: dict[str, set[str]]) -> None:
    got = {table: set(spec["columns"]) for table, spec in policy["tables"].items()}
    assert got == expected
    assert {(row["table"], row["column"]) for row in plan} == {
        (table, column) for table, columns in expected.items() for column in columns
    }


def test_health_hand_plan_contract() -> None:
    policy, plan = health_plan()
    _covered(policy, plan, _HEALTH_COLUMNS)
    first = generate(policy, plan)
    second = generate(policy, list(reversed(plan)))
    assert digest(first) == digest(second)
    assert set(first["files"]) == {"ed_visits.csv", "lab_results.csv"}
    visits = first["files"]["ed_visits.csv"]
    assert "age_band" in visits["columns"]
    assert "date_of_birth" not in visits["columns"]
    assert visits["columns"]["age_band"]["params"]["derived_from"] == "date_of_birth"
    assert visits["columns"]["arrival_ts"]["form"] == MONTH_HOUR_FORM
    assert visits["required"] == [
        "age_band", "arrival_ts", "icd10_primary", "los_minutes", "municipality", "readmit_30d",
        "temp_c", "triage", "visit_id",
    ]
    qi = {(row["table"], row["column"]): row["derived_from"] for row in first["qi"]}
    assert qi["ed_visits", "age_band"] == "date_of_birth"
    assert ("lab_results", "sampled_ts") not in qi
    scopes = {(row["table"], row["column"]): row["scope"] for row in first["tokens"]}
    assert scopes["ed_visits", "visit_id"] == "release"
    assert scopes["lab_results", "visit_id"] == "release"
    assert all(body["form"] for spec in first["files"].values() for body in spec["columns"].values())
    names = set(visits["columns"]) | set(first["files"]["lab_results.csv"]["columns"])
    for absent in ("patient_hetu", "patient_name", "phone", "home_address", "postcode",
                   "chief_complaint", "attending_physician_name", "discharge_ts", "sampled_ts"):
        assert absent not in names


def test_cs_hand_plan_contract() -> None:
    policy, plan = cs_plan()
    _covered(policy, plan, _CS_COLUMNS)
    contract = generate(policy, plan)
    assert set(contract["files"]) == {"conversations.csv", "turns.csv"}
    conversations = contract["files"]["conversations.csv"]
    turns = contract["files"]["turns.csv"]
    assert "split" in conversations["required"]
    assert conversations["required"] == ["conversation_id", "handle_time_s", "intent", "split"]
    assert turns["required"] == ["conversation_id", "text", "turn_id"]
    assert conversations["columns"]["started_ts"]["form"] == r"^\d{4}-\d{2}-\d{2}T\d{2}:00$"
    assert turns["columns"]["ts"]["form"] == r"^\d{4}-\d{2}-\d{2}T\d{2}:00$"
    assert turns["columns"]["text"]["form"]
    assert "text" not in {row["column"] for row in contract["tokens"]}
    scopes = {(row["table"], row["column"]): row["scope"] for row in contract["tokens"]}
    assert scopes["conversations", "conversation_id"] == "release"
    assert scopes["turns", "conversation_id"] == "release"
    assert conversations["columns"]["conversation_id"]["form"] == TOKEN_FORM
    assert turns["columns"]["conversation_id"]["form"] == TOKEN_FORM
    names = set(conversations["columns"]) | set(turns["columns"])
    for absent in ("customer_id", "agent_name", "agent_note"):
        assert absent not in names


def test_render_prints_schema_names_and_forms_only() -> None:
    text = render()
    assert "scenario HEALTH-S1 digest " in text
    assert "scenario CS-S1 digest " in text
    assert "column age_band " in text
    assert MONTH_HOUR_FORM in text
    assert "absent_table clinical_notes" in text
    assert "absent_table published_weekly_stats" in text
    assert "absent_table customers" in text
    assert "absent_column ed_visits.patient_hetu" in text
    assert "renamed ed_visits.date_of_birth age_band" in text
    assert "column date_of_birth " not in text
