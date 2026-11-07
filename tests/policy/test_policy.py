"""Scenario policy + hand plans (ticket 09). Schema names only; no row values."""
import json

import pytest

from pets_release.policy import (
    PlanError,
    get_policy,
    hand_plan,
    validate_plan,
)

HEALTH_COLS = {
    "ed_visits": "visit_id,patient_hetu,patient_name,date_of_birth,sex,phone,home_address,postcode,municipality,"
    "arrival_ts,arrival_mode,ambulance_unit,triage,chief_complaint,icd10_primary,icd10_secondary,systolic_bp,"
    "diastolic_bp,heart_rate,resp_rate,temp_c,spo2,pain_nrs,attending_physician_id,attending_physician_name,"
    "discharge_ts,los_minutes,disposition,readmit_30d",
    "lab_results": "lab_id,visit_id,test_code,test_name,value,unit,ref_range,abnormal_flag,sampled_ts",
    "clinical_notes": "note_id,visit_id,note_type,author_staff_id,author_name,written_ts,language,note_text",
    "published_weekly_stats": "stat_id,week,municipality,age_band,sex,diagnosis_group,visits",
}
CS_COLS = {
    "conversations": "conversation_id,customer_id,agent_id,agent_name,channel,language,started_ts,intent,sentiment,"
    "csat,resolved,handle_time_s,n_turns,split,agent_note",
    "customers": "customer_id,customer_number,full_name,hetu,street_address,postcode,city,email,phone,"
    "preferred_language,customer_since,products,contract_number,payment_method,iban,marketing_consent,"
    "payment_default_flag,accessibility_needs",
    "turns": "turn_id,conversation_id,seq,speaker,ts,text",
}
SRC = {
    "HEALTH-S1": {t: c.split(",") for t, c in HEALTH_COLS.items()},
    "CS-S1": {t: c.split(",") for t, c in CS_COLS.items()},
}
DIRECT = {
    "HEALTH-S1": [
        ("ed_visits", c)
        for c in ["patient_hetu", "patient_name", "phone", "home_address", "attending_physician_name"]
    ]
    + [("clinical_notes", "author_name")],
    "CS-S1": [("customers", c) for c in SRC["CS-S1"]["customers"]]
    + [("conversations", "customer_id"), ("conversations", "agent_name")],
}
SIDS = ["HEALTH-S1", "CS-S1"]


def idx(plan):
    return {(e["table"], e["column"]): e for e in plan}


@pytest.mark.parametrize("sid", SIDS)
def test_every_source_column_has_a_floor(sid):
    pol = get_policy(sid)
    for t, cols in SRC[sid].items():
        for c in cols:
            assert (t, c) in pol.floors, (t, c)
    assert set(pol.floors) == {(t, c) for t, cs in SRC[sid].items() for c in cs}


@pytest.mark.parametrize("sid", SIDS)
def test_direct_identifier_floors_are_pseudonym_or_withheld(sid):
    pol = get_policy(sid)
    for key in DIRECT[sid]:
        assert pol.floors[key].rung in ("pseudonym", "withheld"), key
    for key in pol.direct_identifiers:
        assert pol.floors[key].rung in ("pseudonym", "withheld"), key


@pytest.mark.parametrize("sid", SIDS)
def test_hand_plan_covers_all_columns_and_validates(sid):
    plan = hand_plan(sid)
    validate_plan(plan, get_policy(sid))
    assert {(e["table"], e["column"]) for e in plan} == set(get_policy(sid).floors)
    assert all(e["source"] == "hand" for e in plan)
    assert len(plan) == len({(e["table"], e["column"]) for e in plan})


@pytest.mark.parametrize("sid", SIDS)
def test_hand_plan_never_finer_than_floor_and_direct_ids_withheld_or_pseudo(sid):
    pol = get_policy(sid)
    for e in hand_plan(sid):
        assert e["floor"] == pol.floors[(e["table"], e["column"])].rung
    ix = idx(hand_plan(sid))
    for key in DIRECT[sid]:
        assert ix[key]["rung"] == "withheld"


def test_health_hand_plan_matches_spec_table():
    ix = idx(hand_plan("HEALTH-S1"))
    for t in ("clinical_notes", "published_weekly_stats"):
        assert all(e["rung"] == "withheld" for e in hand_plan("HEALTH-S1") if e["table"] == t)
    for c in ("chief_complaint", "postcode", "patient_hetu", "patient_name", "phone", "home_address",
              "attending_physician_name"):
        assert ix[("ed_visits", c)]["rung"] == "withheld"
    dob = ix[("ed_visits", "date_of_birth")]
    assert dob["rung"] in ("age_band_5", "age_band_10")
    assert dob["params"]["derived_column"] == "age_band"
    assert dob["params"]["top_code"] == 90
    assert ix[("ed_visits", "visit_id")]["rung"] == "pseudonym"
    assert ix[("lab_results", "visit_id")]["rung"] == "pseudonym"
    assert ix[("lab_results", "visit_id")]["params"] == ix[("ed_visits", "visit_id")]["params"]
    assert ix[("ed_visits", "arrival_ts")]["rung"] == "month_hour"
    assert ix[("ed_visits", "municipality")]["rung"] == "top_n"
    assert ix[("ed_visits", "municipality")]["params"]["n"] >= 8
    assert ix[("ed_visits", "readmit_30d")]["rung"] == "exact"
    assert ix[("ed_visits", "triage")]["rung"] == "exact"


def test_health_policy_contents():
    pol = get_policy("HEALTH-S1")
    assert list(pol.purpose_checks) == ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"]
    k = [t for t in pol.privacy_targets if t["kind"] == "k_anonymity"][0]
    assert k["k"] == 5 and k["unit"] == "persons"
    assert {(q["table"], q["column"]) for q in pol.qi} >= {
        ("ed_visits", "date_of_birth"), ("ed_visits", "sex"), ("ed_visits", "municipality"),
        ("ed_visits", "arrival_ts"),
    }
    assert pol.floors[("ed_visits", "patient_hetu")].rung == "withheld"
    assert pol.floors[("ed_visits", "ambulance_unit")].rung == "pseudonym"
    assert pol.floors[("ed_visits", "attending_physician_id")].rung == "pseudonym"
    assert pol.floors[("lab_results", "sampled_ts")].rung == "exact"
    assert any("join" in q.get("note", "") for q in pol.qi if q["column"] == "sampled_ts")


def test_cs_hand_plan_matches_spec_table():
    ix = idx(hand_plan("CS-S1"))
    assert all(e["rung"] == "withheld" for e in hand_plan("CS-S1") if e["table"] == "customers")
    for c in ("customer_id", "agent_name", "agent_note"):
        assert ix[("conversations", c)]["rung"] == "withheld"
    assert ix[("conversations", "split")]["rung"] == "exact"
    assert ix[("conversations", "started_ts")]["rung"] == "hour"
    assert ix[("turns", "ts")]["rung"] == "hour"
    assert ix[("turns", "text")]["rung"] == "redacted"
    assert ix[("conversations", "conversation_id")]["rung"] == "pseudonym"
    assert ix[("conversations", "conversation_id")]["params"] == ix[("turns", "conversation_id")]["params"]
    assert ix[("turns", "turn_id")]["params"]["requires_check"] == "turn-id-synthetic"
    assert ix[("turns", "turn_id")]["params"]["fallback_rung"] == "pseudonym"


def test_cs_policy_contents():
    pol = get_policy("CS-S1")
    assert list(pol.purpose_checks) == ["CS-U1", "CS-U3", "CS-U4", "CS-U5"]
    kinds = {t["kind"] for t in pol.privacy_targets}
    assert {"text_recall", "health_in_text", "timestamp_floor"} <= kinds
    rec = [t for t in pol.privacy_targets if t["kind"] == "text_recall"][0]
    assert rec["min"] == 0.98
    assert set(rec["labels"]) == {"NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET"}
    assert pol.qi == ()
    assert pol.floors[("turns", "ts")].rung == "hour"
    assert pol.floors[("conversations", "started_ts")].rung == "hour"
    assert pol.floors[("conversations", "agent_id")].rung == "pseudonym"


@pytest.mark.parametrize("sid", SIDS)
def test_sacrifices_and_moves_are_enumerated_and_well_formed(sid):
    pol = get_policy(sid)
    for s in pol.sacrifices:
        assert s["check"] in pol.purpose_checks
        assert 0.0 <= s["floor_score"] < 0.9
        assert s["reason"]
    assert len({s["check"] for s in pol.sacrifices}) == len(pol.sacrifices)
    assert pol.risk_vector and len(set(pol.risk_vector)) == len(pol.risk_vector)
    for move in pol.joint_qi_moves:
        for m in move:
            assert (m["table"], m["column"]) in pol.floors
    if sid == "HEALTH-S1":
        assert pol.joint_qi_moves
    else:
        assert pol.joint_qi_moves == ()


@pytest.mark.parametrize("sid", SIDS)
def test_policy_and_plan_are_json_serialisable_and_deterministic(sid):
    a = json.dumps(get_policy(sid).to_json(), sort_keys=True)
    b = json.dumps(get_policy(sid).to_json(), sort_keys=True)
    assert a == b
    assert json.dumps(hand_plan(sid), sort_keys=True) == json.dumps(hand_plan(sid), sort_keys=True)
    # entries are plain dicts with the pinned keys
    for e in hand_plan(sid):
        assert set(e) == {"table", "column", "rung", "params", "floor", "reason", "source"}
        assert e["reason"]


def test_unknown_scenario_raises():
    with pytest.raises(KeyError):
        get_policy("NOPE")
    with pytest.raises(KeyError):
        hand_plan("HEALTH-S2")


# ---- validate_plan: every failure row from trigger to result ----
def _mutated(sid, fn):
    plan = [dict(e, params=dict(e["params"])) for e in hand_plan(sid)]
    fn(plan)
    return plan


def test_validate_rejects_missing_column():
    p = _mutated("HEALTH-S1", lambda pl: pl.pop(0))
    with pytest.raises(PlanError, match="missing"):
        validate_plan(p, get_policy("HEALTH-S1"))


def test_validate_rejects_extra_and_duplicate_column():
    p = _mutated("HEALTH-S1", lambda pl: pl.append(dict(pl[0], column="invented")))
    with pytest.raises(PlanError, match="unknown"):
        validate_plan(p, get_policy("HEALTH-S1"))
    p = _mutated("HEALTH-S1", lambda pl: pl.append(dict(pl[0])))
    with pytest.raises(PlanError, match="duplicate"):
        validate_plan(p, get_policy("HEALTH-S1"))


def test_validate_rejects_unknown_key_and_missing_key_and_bad_source():
    p = _mutated("CS-S1", lambda pl: pl[0].update(extra=1))
    with pytest.raises(PlanError, match="keys"):
        validate_plan(p, get_policy("CS-S1"))
    p = _mutated("CS-S1", lambda pl: pl[0].pop("reason"))
    with pytest.raises(PlanError, match="keys"):
        validate_plan(p, get_policy("CS-S1"))
    p = _mutated("CS-S1", lambda pl: pl[0].update(source="llm"))
    with pytest.raises(PlanError, match="source"):
        validate_plan(p, get_policy("CS-S1"))


def test_validate_rejects_rung_finer_than_floor():
    def raw_ts(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("turns", "ts"):
                e["rung"] = "exact"
    with pytest.raises(PlanError, match="floor"):
        validate_plan(_mutated("CS-S1", raw_ts), get_policy("CS-S1"))


def test_validate_rejects_raw_direct_identifier_and_unknown_rung():
    def raw_name(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("ed_visits", "patient_name"):
                e["rung"] = "exact"
    with pytest.raises(PlanError):
        validate_plan(_mutated("HEALTH-S1", raw_name), get_policy("HEALTH-S1"))

    def bogus(pl):
        pl[0]["rung"] = "bogus"
    with pytest.raises(PlanError, match="rung"):
        validate_plan(_mutated("HEALTH-S1", bogus), get_policy("HEALTH-S1"))


def test_validate_rejects_changed_floor_field():
    def f(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("ed_visits", "postcode"):
                e["floor"] = "exact"
    with pytest.raises(PlanError, match="floor"):
        validate_plan(_mutated("HEALTH-S1", f), get_policy("HEALTH-S1"))


def test_validate_rejects_non_json_params_and_empty_reason():
    p = _mutated("HEALTH-S1", lambda pl: pl[0].update(params={"x": {1, 2}}))
    with pytest.raises(PlanError, match="params"):
        validate_plan(p, get_policy("HEALTH-S1"))
    p = _mutated("HEALTH-S1", lambda pl: pl[0].update(reason=""))
    with pytest.raises(PlanError, match="reason"):
        validate_plan(p, get_policy("HEALTH-S1"))


def test_validate_rejects_mismatched_pseudonym_scope_across_joined_tables():
    def f(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("lab_results", "visit_id"):
                e["params"] = {"scope": "conversation"}
    with pytest.raises(PlanError, match="scope"):
        validate_plan(_mutated("HEALTH-S1", f), get_policy("HEALTH-S1"))


def test_validate_rejects_top_n_below_policy_minimum():
    def f(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("ed_visits", "municipality"):
                e["params"] = {"n": 3}
    with pytest.raises(PlanError, match="top_n"):
        validate_plan(_mutated("HEALTH-S1", f), get_policy("HEALTH-S1"))


def test_validate_rejects_released_column_of_withheld_table():
    def f(pl):
        for e in pl:
            if e["table"] == "customers" and e["column"] == "customer_id":
                e["rung"] = "pseudonym"
    # floor for customers.customer_id is withheld -> finer than floor
    with pytest.raises(PlanError):
        validate_plan(_mutated("CS-S1", f), get_policy("CS-S1"))


def test_no_row_like_values_in_serialised_artefacts():
    # content-free: only schema words; no digits-heavy tokens like ids or dates
    import re
    for sid in SIDS:
        blob = json.dumps([get_policy(sid).to_json(), hand_plan(sid)])
        assert not re.search(r"\d{6,}", blob)
        assert not re.search(r"@|\d{4}-\d{2}-\d{2}", blob)
