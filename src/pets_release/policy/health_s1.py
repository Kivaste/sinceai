"""HEALTH-S1 policy and hand-picked plan (walking skeleton). Spec #1, per-column table."""
from __future__ import annotations

from ._build import build, withheld_table
from .model import ScenarioPolicy

REL = {"label": "RECORD_KEY"}
D = "direct identifier"


def _r(t, c, fam, floor, direct, freason, hrung=None, hparams=None, hreason=None):
    return (t, c, fam, floor, direct, freason, hrung or floor, hparams or {}, hreason or freason)


E = "ed_visits"
L = "lab_results"
_ROWS = [
    _r(E, "visit_id", "identifier", "pseudonym", False, "release-scope pseudonym, identical in lab_results (H-U7 join)", "pseudonym", REL),
    _r(E, "patient_hetu", "identifier", "withheld", True, "linkage handle; pseudonym only if the search shows readmit_30d alone fails H-U6"),
    _r(E, "patient_name", "identifier", "withheld", True, D),
    _r(E, "phone", "identifier", "withheld", True, D),
    _r(E, "home_address", "identifier", "withheld", True, D),
    _r(E, "attending_physician_name", "identifier", "withheld", True, D),
    _r(E, "date_of_birth", "age", "age_band_5", False, "QI; released only as derived column age_band (H-U6)",
       "age_band_10", {"ref_column": "arrival_ts", "output": "age_band"}, "10-year band, top-coded 90+, serves H-U6 and k"),
    _r(E, "sex", "categorical", "exact", False, "QI", "withheld", {}, "no check needs it; withheld to raise per-person k"),
    _r(E, "postcode", "geo", "withheld", False, "municipality suffices"),
    _r(E, "municipality", "geo", "exact", False, "QI; H-U4 needs the eight largest municipalities",
       "top_n", {"n": 8}, "H-U4 needs the top 8; rest grouped as other to help k"),
    _r(E, "arrival_ts", "timestamp", "exact", False, "QI; H-U8 hour-of-day vs k on arrival week",
       "hour_of_day", {}, "hour of day only: H-U8 needs the hour-of-day curve; no date raises per-person k"),
    _r(E, "arrival_mode", "categorical", "exact", False, "QI (kit dictionary role); no required check", "withheld", {}, "no check needs it; withheld to raise per-person k"),
    _r(E, "ambulance_unit", "identifier", "pseudonym", False, "technical identifier", "withheld", {}, "no check needs it"),
    _r(E, "triage", "categorical", "exact", False, "H-U2", "exact"),
    _r(E, "chief_complaint", "text", "withheld", False, "free text, no check needs it"),
    _r(E, "icd10_primary", "icd10", "exact", False, "H-U4, H-U7", "chars3", {}, "diagnosis groups need 3 characters at most"),
    _r(E, "icd10_secondary", "icd10", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "systolic_bp", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "diastolic_bp", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "heart_rate", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "resp_rate", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "temp_c", "numeric", "exact", False, "H-U7 CRP vs temperature", "exact"),
    _r(E, "spo2", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "pain_nrs", "numeric", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(E, "attending_physician_id", "identifier", "pseudonym", False, "technical identifier", "withheld", {}, "no check needs it"),
    _r(E, "discharge_ts", "timestamp", "exact", False, "no required check", "withheld", {}, "no check needs it; los_minutes carries H-U2"),
    _r(E, "los_minutes", "numeric", "exact", False, "H-U2", "exact"),
    _r(E, "disposition", "categorical", "exact", False, "no required check", "exact"),
    _r(E, "readmit_30d", "categorical", "exact", False, "H-U6", "exact"),
    _r(L, "visit_id", "identifier", "pseudonym", False, "same pseudonym as ed_visits (H-U7 join)", "pseudonym", REL),
    _r(L, "lab_id", "identifier", "pseudonym", False, "record key", "pseudonym", REL),
    _r(L, "test_code", "categorical", "exact", False, "H-U7 (CRP)"),
    _r(L, "test_name", "categorical", "exact", False, "H-U7 (CRP)"),
    _r(L, "value", "numeric", "exact", False, "H-U7 (CRP)"),
    _r(L, "unit", "categorical", "exact", False, "H-U7 (CRP)"),
    _r(L, "ref_range", "categorical", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(L, "abnormal_flag", "categorical", "exact", False, "no required check", "withheld", {}, "no check needs it"),
    _r(L, "sampled_ts", "timestamp", "exact", False, "if released, a join-derived QI (arrival-date leak via join)",
       "withheld", {}, "no check needs it; avoids join-derived QI"),
]
_NOTE = "no purpose check needs it"
_ROWS += withheld_table("clinical_notes", [
    ("note_id", "identifier"), ("visit_id", "identifier"), ("note_type", "categorical"),
    ("author_staff_id", "identifier"), ("author_name", "identifier"), ("written_ts", "timestamp"),
    ("language", "categorical"), ("note_text", "text"),
], "table withheld: " + _NOTE)
_ROWS += withheld_table("published_weekly_stats", [
    ("stat_id", "identifier"), ("week", "categorical"), ("municipality", "geo"), ("age_band", "categorical"),
    ("sex", "categorical"), ("diagnosis_group", "categorical"), ("visits", "numeric"),
], "table withheld: " + _NOTE + "; unsuppressed, a differencing aid")

FLOORS, DIRECT, _PLAN = build(_ROWS)
# clinical_notes.author_name is a staff direct identifier (floor withheld)
DIRECT = tuple(sorted(set(DIRECT) | {("clinical_notes", "author_name")}))

POLICY = ScenarioPolicy(
    scenario="HEALTH-S1",
    dataset="health",
    purpose_checks=("H-U2", "H-U4", "H-U6", "H-U7", "H-U8"),
    privacy_targets=(
        {"id": "qi-k", "kind": "k_anonymity", "k": 5, "unit": "persons",
         "over": "every released QI incl. hour and join-derived information"},
    ),
    residual_notes=(
        {"id": "free-text-recall", "status": "not_applicable",
         "note": "scenario text-recall target (PERSON, PHONE, ADDRESS, NATIONAL_ID >= 0.95) is vacuous: no free text is released"},
    ),
    suppression={
        "method": "local_suppression", "unit": "persons", "k": 5, "max_share": 0.10,
        "order": "record_key_ascending_iterate_to_fixpoint",
        "then": "full_recheck_of_every_purpose_check_and_privacy_target",
    },
    floors=FLOORS,
    direct_identifiers=DIRECT,
    qi=(
        {"table": "ed_visits", "column": "date_of_birth", "derived": "age_band"},
        {"table": "ed_visits", "column": "sex", "derived": "sex"},
        {"table": "ed_visits", "column": "municipality", "derived": "municipality"},
        {"table": "ed_visits", "column": "arrival_ts", "derived": "arrival_ts"},
        {"table": "ed_visits", "column": "arrival_mode", "derived": "arrival_mode",
         "note": "conditional QI (kit dictionary role quasi_identifier): counted if released"},
        {"table": "ed_visits", "column": "ambulance_unit", "derived": "ambulance_unit",
         "note": "conditional QI (kit dictionary role quasi_identifier): counted if released as a pseudonym"},
        {"table": "ed_visits", "column": "discharge_ts", "derived": "discharge_ts",
         "note": "conditional QI: counted if released; visit timing (arrival + stay)"},
        {"table": "lab_results", "column": "sampled_ts", "derived": "sampled_ts",
         "join_via": ["ed_visits", "visit_id"],
         "note": "conditional QI: counted as a join-derived QI if released (arrival-date leak via visit join)"},
    ),
    risk_vector=("qi_k_shortfall", "qi_unique_rate", "join_derived_qi", "direct_identifier_leak", "attribute_inference"),
    sacrifices=(
        {"check": "H-U4", "floor_score": 0.6, "reason": "municipality grouping to top-N to reach k", "via": [{"table": "ed_visits", "column": "municipality"}]},
        {"check": "H-U6", "floor_score": 0.6, "reason": "coarser age band to reach k", "via": [{"table": "ed_visits", "column": "date_of_birth"}]},
        {"check": "H-U8", "floor_score": 0.6, "reason": "coarser arrival time to reach k", "via": [{"table": "ed_visits", "column": "arrival_ts"}]},
    ),
    joint_qi_moves=(
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age.band10"},
         {"table": "ed_visits", "column": "municipality", "rung": "geo.topn"}),
        ({"table": "ed_visits", "column": "arrival_ts", "rung": "ts.month_hour"},
         {"table": "ed_visits", "column": "municipality", "rung": "geo.topn"}),
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age.band10"},
         {"table": "ed_visits", "column": "arrival_ts", "rung": "ts.day"}),
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age.band10"},
         {"table": "ed_visits", "column": "municipality", "rung": "geo.topn"},
         {"table": "ed_visits", "column": "arrival_ts", "rung": "ts.month_hour"}),
    ),
    linked=((("ed_visits", "visit_id"), ("lab_results", "visit_id")),),
    alt_floors={("ed_visits", "patient_hetu"): "id.pseudonym"},
    param_minimums={("ed_visits", "municipality"): {"rung": "geo.topn", "param": "n", "min": 8}},
)


def hand_plan() -> list:
    return [dict(e, params=dict(e["params"])) for e in _PLAN]
