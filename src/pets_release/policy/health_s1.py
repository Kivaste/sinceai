"""HEALTH-S1 policy and hand-picked plan (walking skeleton). Spec #1, per-column table."""
from __future__ import annotations

from ._build import build, withheld_table
from .model import ScenarioPolicy

REL = {"scope": "release"}
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
       "age_band_10", {"derived_column": "age_band", "top_code": 90}, "10-year band, top-coded 90+, serves H-U6 and k"),
    _r(E, "sex", "categorical", "exact", False, "QI", "exact"),
    _r(E, "postcode", "geo", "withheld", False, "municipality suffices"),
    _r(E, "municipality", "geo", "exact", False, "QI; H-U4 needs the eight largest municipalities",
       "top_n", {"n": 8}, "H-U4 needs the top 8; rest grouped as other to help k"),
    _r(E, "arrival_ts", "timestamp", "exact", False, "QI; H-U8 hour-of-day vs k on arrival week",
       "month_hour", {}, "month+hour keeps the hour-of-day curve, collapses the date"),
    _r(E, "arrival_mode", "categorical", "exact", False, "no required check; kept low-risk", "exact"),
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
        {"id": "free-text-recall", "kind": "text_recall", "min": 0.95,
         "labels": ["PERSON", "PHONE", "ADDRESS", "NATIONAL_ID"],
         "note": "vacuous here: no free text is released; recorded as a residual-risk note"},
    ),
    floors=FLOORS,
    direct_identifiers=DIRECT,
    qi=(
        {"table": "ed_visits", "column": "date_of_birth", "derived": "age_band"},
        {"table": "ed_visits", "column": "sex", "derived": "sex"},
        {"table": "ed_visits", "column": "municipality", "derived": "municipality"},
        {"table": "ed_visits", "column": "arrival_ts", "derived": "arrival_ts"},
        {"table": "lab_results", "column": "sampled_ts", "derived": "sampled_ts",
         "note": "counted as a join-derived QI if released"},
    ),
    risk_vector=("qi_k_shortfall", "qi_unique_rate", "join_derived_qi", "direct_identifier_leak", "attribute_inference"),
    sacrifices=(
        {"check": "H-U4", "floor_score": 0.6, "reason": "municipality grouping to top-N to reach k"},
        {"check": "H-U6", "floor_score": 0.6, "reason": "coarser age band to reach k"},
        {"check": "H-U8", "floor_score": 0.6, "reason": "coarser arrival time to reach k"},
    ),
    joint_qi_moves=(
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age_band_10"},
         {"table": "ed_visits", "column": "municipality", "rung": "top_n"}),
        ({"table": "ed_visits", "column": "arrival_ts", "rung": "month_hour"},
         {"table": "ed_visits", "column": "municipality", "rung": "top_n"}),
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age_band_10"},
         {"table": "ed_visits", "column": "arrival_ts", "rung": "day"}),
        ({"table": "ed_visits", "column": "date_of_birth", "rung": "age_band_10"},
         {"table": "ed_visits", "column": "municipality", "rung": "top_n"},
         {"table": "ed_visits", "column": "arrival_ts", "rung": "month_hour"}),
    ),
    linked=((("ed_visits", "visit_id"), ("lab_results", "visit_id")),),
    param_minimums={("ed_visits", "municipality"): {"rung": "top_n", "param": "n", "min": 8}},
)


def hand_plan() -> list:
    return [dict(e, params=dict(e["params"])) for e in _PLAN]
