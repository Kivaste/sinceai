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
        assert pol.floors[key].rung in ("id.pseudonym", "withheld"), key
    for key in pol.direct_identifiers:
        assert pol.floors[key].rung in ("id.pseudonym", "withheld"), key


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
    assert dob["rung"] in ("age.band5", "age.band10")
    assert dob["params"]["output"] == "age_band"
    assert dob["params"]["ref_column"] == "arrival_ts"
    assert ix[("ed_visits", "visit_id")]["rung"] == "id.pseudonym"
    assert ix[("lab_results", "visit_id")]["rung"] == "id.pseudonym"
    assert ix[("lab_results", "visit_id")]["params"] == ix[("ed_visits", "visit_id")]["params"]
    assert ix[("ed_visits", "arrival_ts")]["rung"] == "ts.hour_of_day"
    assert ix[("ed_visits", "municipality")]["rung"] == "geo.topn"
    assert ix[("ed_visits", "municipality")]["params"]["n"] >= 8
    assert ix[("ed_visits", "readmit_30d")]["rung"] == "keep"
    assert ix[("ed_visits", "triage")]["rung"] == "keep"


def test_health_policy_contents():
    pol = get_policy("HEALTH-S1")
    assert list(pol.purpose_checks) == ["H-U2", "H-U4", "H-U6", "H-U7", "H-U8"]
    k = next(t for t in pol.privacy_targets if t["kind"] == "k_anonymity")
    assert k["k"] == 5 and k["unit"] == "persons"
    assert {(q["table"], q["column"]) for q in pol.qi} >= {
        ("ed_visits", "date_of_birth"), ("ed_visits", "sex"), ("ed_visits", "municipality"),
        ("ed_visits", "arrival_ts"),
    }
    assert pol.floors[("ed_visits", "patient_hetu")].rung == "withheld"
    assert pol.floors[("ed_visits", "ambulance_unit")].rung == "id.pseudonym"
    assert pol.floors[("ed_visits", "attending_physician_id")].rung == "id.pseudonym"
    assert pol.floors[("lab_results", "sampled_ts")].rung == "ts.exact"
    assert any("join" in q.get("note", "") for q in pol.qi if q["column"] == "sampled_ts")


def test_cs_hand_plan_matches_spec_table():
    ix = idx(hand_plan("CS-S1"))
    assert all(e["rung"] == "withheld" for e in hand_plan("CS-S1") if e["table"] == "customers")
    for c in ("customer_id", "agent_name", "agent_note"):
        assert ix[("conversations", c)]["rung"] == "withheld"
    assert ix[("conversations", "split")]["rung"] == "keep"
    assert ix[("conversations", "started_ts")]["rung"] == "ts.hour"
    assert ix[("turns", "ts")]["rung"] == "ts.hour"
    assert ix[("turns", "text")]["rung"] == "text.redacted"
    assert ix[("conversations", "conversation_id")]["rung"] == "id.pseudonym"
    assert ix[("conversations", "conversation_id")]["params"] == ix[("turns", "conversation_id")]["params"]
    assert ix[("turns", "turn_id")]["params"]["requires_check"] == "turn-id-synthetic"
    assert ix[("turns", "turn_id")]["params"]["fallback_rung"] == "id.pseudonym"


def test_cs_policy_contents():
    pol = get_policy("CS-S1")
    assert list(pol.purpose_checks) == ["CS-U1", "CS-U3", "CS-U4", "CS-U5"]
    kinds = {t["kind"] for t in pol.privacy_targets}
    assert {"text_recall", "health_in_text", "timestamp_floor"} <= kinds
    rec = next(t for t in pol.privacy_targets if t["kind"] == "text_recall")
    assert rec["min"] == 0.98
    assert set(rec["labels"]) == {"NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET"}
    assert pol.qi == ()
    assert pol.floors[("turns", "ts")].rung == "ts.hour"
    assert pol.floors[("conversations", "started_ts")].rung == "ts.hour"
    assert pol.floors[("conversations", "agent_id")].rung == "id.pseudonym"


@pytest.mark.parametrize("sid", SIDS)
def test_sacrifices_and_moves_are_enumerated_and_well_formed(sid):
    pol = get_policy(sid)
    for s in pol.sacrifices:
        assert s["check"] in pol.purpose_checks
        assert 0.0 <= s["floor_score"] < 0.9
        assert s["reason"]
        assert s["via"] and all((v["table"], v["column"]) in pol.floors for v in s["via"])
        assert any(pol.floors[(v["table"], v["column"])].rung != "withheld" for v in s["via"])
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
                e["rung"] = "ts.exact"
    with pytest.raises(PlanError, match="floor"):
        validate_plan(_mutated("CS-S1", raw_ts), get_policy("CS-S1"))


def test_validate_rejects_raw_direct_identifier_and_unknown_rung():
    def raw_name(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("ed_visits", "patient_name"):
                e["rung"] = "ts.exact"
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
                e["floor"] = "ts.exact"
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
                e["params"] = {"label": "OTHER"}
    with pytest.raises(PlanError, match="linked"):
        validate_plan(_mutated("HEALTH-S1", f), get_policy("HEALTH-S1"))


def test_validate_rejects_top_n_below_policy_minimum():
    def f(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("ed_visits", "municipality"):
                e["params"] = {"n": 3}
    with pytest.raises(PlanError, match="topn"):
        validate_plan(_mutated("HEALTH-S1", f), get_policy("HEALTH-S1"))


def test_validate_rejects_released_column_of_withheld_table():
    def f(pl):
        for e in pl:
            if e["table"] == "customers" and e["column"] == "customer_id":
                e["rung"] = "id.pseudonym"
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


def test_ladders_07_apply_accepts_hand_plans_on_synthetic_frames():
    """Production check: ticket 07's real apply must accept the plan shape (hand-made rows)."""
    import pandas as pd

    from pets_release.ladders import apply

    class K:
        def token(self, value, label="RECORD_KEY"):
            return "a" * 64

    def frames(sid, red):
        out = {}
        for t, cols in SRC[sid].items():
            out[t] = pd.DataFrame({c: ["x1"] * 3 for c in cols})
        return out

    h = frames("HEALTH-S1", None)
    h["ed_visits"]["date_of_birth"] = ["1980-05-01", "1990-01-01", "1950-02-02"]
    h["ed_visits"]["arrival_ts"] = ["2025-03-04T14:30:00"] * 3
    h["ed_visits"]["municipality"] = ["A", "B", "A"]
    h["ed_visits"]["icd10_primary"] = ["J10.1", "A09", "S72.0"]
    out = apply(hand_plan("HEALTH-S1"), h, K())
    assert "age_band" in out["ed_visits"].columns and "date_of_birth" not in out["ed_visits"].columns
    assert set(out) == {"ed_visits", "lab_results"}

    c = frames("CS-S1", None)
    for t, col in (("conversations", "started_ts"), ("turns", "ts")):
        c[t][col] = ["2025-03-04T14:30:00"] * 3
    out = apply(hand_plan("CS-S1"), c, K(), redactor=lambda t, col, df, p: df[col])
    assert set(out) == {"conversations", "turns"}


def test_turn_id_fallback_plan_validates_and_is_accepted_by_apply():
    from pets_release.policy.cs_s1 import turn_id_fallback_plan
    plan = turn_id_fallback_plan(hand_plan("CS-S1"))
    validate_plan(plan, get_policy("CS-S1"))
    e = idx(plan)[("turns", "turn_id")]
    assert e["rung"] == "id.pseudonym" and e["floor"] == "id.pseudonym"


def test_policy_rung_ids_are_07_ids():
    from pets_release.ladders import CONTRACT_FORMS, WITHHELD
    for sid in SIDS:
        for e in hand_plan(sid):
            assert e["rung"] in CONTRACT_FORMS or e["rung"] == WITHHELD
            assert e["floor"] in CONTRACT_FORMS or e["floor"] == WITHHELD

def test_every_releasable_timing_age_geo_column_is_a_qi_under_a_k_target():
    """Regression: discharge_ts (exact floor) was missing from the HEALTH-S1 QI set."""
    pol = get_policy("HEALTH-S1")
    qis = {(q["table"], q["column"]) for q in pol.qi}
    for key, fl in pol.floors.items():
        if fl.family in ("timestamp", "age", "geo") and fl.rung != "withheld":
            assert key in qis, key
    assert ("ed_visits", "discharge_ts") in qis


def test_join_derived_qi_declares_join_via():
    pol = get_policy("HEALTH-S1")
    row = next(q for q in pol.qi if (q["table"], q["column"]) == ("lab_results", "sampled_ts"))
    assert row["join_via"] == ["ed_visits", "visit_id"]
    assert ("ed_visits", "visit_id") in pol.floors
    for q in pol.qi:
        if "join_via" in q:
            assert len(q["join_via"]) == 2 and tuple(q["join_via"]) in pol.floors
    assert "joinVia" in str(get_policy("HEALTH-S1").to_json()["qi"]) or "join_via" in str(get_policy("HEALTH-S1").to_json()["qi"])


def test_cs_has_no_k_target_so_no_qi_set():
    pol = get_policy("CS-S1")
    assert not [t for t in pol.privacy_targets if t["kind"] == "k_anonymity"]
    assert pol.qi == ()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_validate_rejects_non_finite_params(bad):
    p = _mutated("HEALTH-S1", lambda pl: pl[0].update(params={"x": bad}))
    with pytest.raises(PlanError, match="params"):
        validate_plan(p, get_policy("HEALTH-S1"))
    p = _mutated("HEALTH-S1", lambda pl: pl[0].update(params={"nested": [{"y": bad}]}))
    with pytest.raises(PlanError, match="params"):
        validate_plan(p, get_policy("HEALTH-S1"))

DICT_QI_ROLES = {  # kit data dictionary quasi_identifier roles (column names only), health tables
    "ed_visits": ["date_of_birth", "sex", "postcode", "municipality", "arrival_ts", "arrival_mode",
                  "ambulance_unit", "discharge_ts"],
    "lab_results": ["sampled_ts"],
    "clinical_notes": ["written_ts", "language"],
    "published_weekly_stats": ["week", "municipality", "age_band", "sex"],
}


def test_every_dictionary_qi_role_releasable_by_floor_is_a_policy_qi():
    pol = get_policy("HEALTH-S1")
    qis = {(q["table"], q["column"]) for q in pol.qi}
    for t, cols in DICT_QI_ROLES.items():
        for c in cols:
            assert (t, c) in pol.floors, (t, c)
            if pol.floors[(t, c)].rung != "withheld":
                assert (t, c) in qis, (t, c)
    assert ("ed_visits", "arrival_mode") in qis and ("ed_visits", "ambulance_unit") in qis


def test_patient_hetu_has_conditional_pseudonym_alt_floor():
    pol = get_policy("HEALTH-S1")
    assert pol.alt_floors[("ed_visits", "patient_hetu")] == "id.pseudonym"
    plan = hand_plan("HEALTH-S1")
    for e in plan:
        if (e["table"], e["column"]) == ("ed_visits", "patient_hetu"):
            e.update(rung="id.pseudonym", floor="id.pseudonym", params={"label": "PERSON_KEY"})
    validate_plan(plan, pol)


def test_alt_floors_serialised():
    j = get_policy("CS-S1").to_json()
    assert j["altFloors"] == [{"table": "turns", "column": "turn_id", "floor": "id.pseudonym"}]
    assert get_policy("HEALTH-S1").to_json()["altFloors"]


def test_alt_branch_rejects_finer_rung_and_still_checks_everything():
    pol = get_policy("CS-S1")
    def f(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("turns", "turn_id"):
                e["floor"] = "id.pseudonym"  # alt floor, but rung stays keep (finer)
    with pytest.raises(PlanError, match="floor"):
        validate_plan(_mutated("CS-S1", f), pol)
    def g(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("turns", "turn_id"):
                e.update(rung="id.pseudonym", floor="id.pseudonym", reason="", params={})
    with pytest.raises(PlanError, match="reason"):
        validate_plan(_mutated("CS-S1", g), pol)
    def h(pl):
        for e in pl:
            if (e["table"], e["column"]) == ("turns", "turn_id"):
                e.update(rung="id.pseudonym", floor="id.pseudonym", params={"label": 5})
    with pytest.raises(PlanError, match="label"):
        validate_plan(_mutated("CS-S1", h), pol)
    def w(pl):  # alt floor with an unrelated (non-alt) column is not honoured
        for e in pl:
            if (e["table"], e["column"]) == ("turns", "seq"):
                e.update(floor="id.pseudonym", rung="id.pseudonym")
    with pytest.raises(PlanError):
        validate_plan(_mutated("CS-S1", w), pol)


def test_cs_has_only_the_cs_u5_sacrifice_and_handle_time_stays_exact():
    pol = get_policy("CS-S1")
    assert [s["check"] for s in pol.sacrifices] == ["CS-U5"]
    assert idx(hand_plan("CS-S1"))[("conversations", "handle_time_s")]["rung"] == "num.exact"


def test_health_free_text_recall_is_a_not_applicable_note_not_a_target():
    pol = get_policy("HEALTH-S1")
    assert not [t for t in pol.privacy_targets if t["kind"] == "text_recall"]
    notes = [n for n in pol.residual_notes if n["id"] == "free-text-recall"]
    assert len(notes) == 1 and notes[0]["status"] == "not_applicable"
    assert pol.to_json()["residualNotes"]
    assert get_policy("CS-S1").residual_notes == ()


def test_health_suppression_policy_field():
    pol = get_policy("HEALTH-S1")
    s = pol.suppression
    assert set(s) == {"method", "unit", "k", "max_share", "order", "then"}
    assert s["method"] == "local_suppression" and s["k"] == 5 and s["unit"] == "persons"
    assert 0 < s["max_share"] <= 0.1
    assert "recheck" in s["then"]
    assert pol.to_json()["suppression"] == s
    assert get_policy("CS-S1").suppression is None


def _bad(sid, **kw):
    import dataclasses

    from pets_release.policy import PolicyError
    pol = get_policy(sid)
    with pytest.raises(PolicyError):
        dataclasses.replace(pol, **kw)


def test_policy_subrecords_are_closed():
    h = get_policy("HEALTH-S1")
    t0, q0, s0, m0 = h.privacy_targets[0], h.qi[0], h.sacrifices[0], h.joint_qi_moves[0]
    _bad("HEALTH-S1", privacy_targets=(dict(t0, extra=1),) + h.privacy_targets[1:])
    _bad("HEALTH-S1", privacy_targets=({k: v for k, v in t0.items() if k != "k"},) + h.privacy_targets[1:])
    _bad("HEALTH-S1", privacy_targets=({"id": "x", "kind": "mystery"},))
    _bad("HEALTH-S1", qi=(dict(q0, extra=1),) + h.qi[1:])
    _bad("HEALTH-S1", qi=({k: v for k, v in q0.items() if k != "derived"},) + h.qi[1:])
    _bad("HEALTH-S1", qi=(dict(q0, column="nope"),) + h.qi[1:])
    _bad("HEALTH-S1", sacrifices=(dict(s0, extra=1),) + h.sacrifices[1:])
    _bad("HEALTH-S1", sacrifices=({k: v for k, v in s0.items() if k != "via"},) + h.sacrifices[1:])
    _bad("HEALTH-S1", sacrifices=(dict(s0, check="H-U99"),) + h.sacrifices[1:])
    _bad("HEALTH-S1", joint_qi_moves=((dict(m0[0], extra=1),) + m0[1:],))
    _bad("HEALTH-S1", joint_qi_moves=((dict(m0[0], rung="nope"),) + m0[1:],))
    _bad("HEALTH-S1", suppression=dict(h.suppression, extra=1))
    _bad("HEALTH-S1", residual_notes=({"id": "x"},))
    c = get_policy("CS-S1")
    _bad("CS-S1", privacy_targets=(dict(c.privacy_targets[0], extra=1),) + c.privacy_targets[1:])