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
       "month_hour", {}, "month and hour: H-U8 needs the hour-of-day curve; the date is dropped to raise per-person k"),
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
    _r(E, "disposition", "categorical", "exact", False,
       "sensitive attribute; all HEALTH-S1 purpose checks exclude cancelled duplicates via kit derive()", "exact"),
    _r(E, "readmit_30d", "categorical", "exact", False, "H-U6", "exact"),
    _r(L, "visit_id", "identifier", "pseudonym", False, "same pseudonym as ed_visits (H-U7 join)", "pseudonym", REL),
    _r(L, "lab_id", "identifier", "pseudonym", False, "record key", "pseudonym", REL),
    _r(L, "test_code", "categorical", "exact", False, "H-U7 (CRP)"),
    _r(L, "test_name", "lab_test", "exact", False, "QI (detector; D33): a person's set of lab tests can single them out",
       "withheld", {}, "no check needs it (H-U7 selects CRP by test_code); as a QI, even its CRP-vs-other rung needs "
       "more local suppression than the cap (measured, #106)"),
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

# D64 (#157): bounded attribute-inference lift. Content-free; stated in the manifest via the residual note below.
MAX_LIFT = 2.0
LOS_BIN_MIN = 30
LIFT_ATTACKER = ("the #139 red-team attribute-inference attacker: knows a released visit's quasi-identifiers and "
                 "guesses the most common released value among the visits that match them; compared with always "
                 "guessing the release's most common value (base rate); seeded sample of at most 3000 targets")
LIFT_REASON = (f"lift = attacker accuracy / base-rate accuracy, at most {MAX_LIFT} for icd10_primary and "
               f"los_minutes: knowing a visit's age band, municipality and arrival hour may at most double the "
               f"chance of guessing its diagnosis or stay. Tighter is not reachable with the purpose floors kept: "
               f"icd10 at chapter level fails H-U4 (measured on the kit, #157), so it stays at 3 characters; "
               f"los_minutes is binned at least {LOS_BIN_MIN} minutes wide (H-U2 still at or above 0.9). "
               f"A plan over the bound is refused, never relaxed")
ATTRIBUTE_LIFT = {"max_lift": MAX_LIFT, "attacker": LIFT_ATTACKER, "reason": LIFT_REASON,
                  "attributes": [{"table": "ed_visits", "column": "icd10_primary"},
                                 {"table": "ed_visits", "column": "los_minutes"}]}
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
        {"id": "sex-withheld", "status": "open",
         "note": "sex is a QI withheld in the hand plan because no purpose check needs it; if a later plan releases it, it counts in per-person k like any released QI"},
        {"id": "renamed-age-band-scorecard-blind-spot", "status": "open",
         "note": "D22: age_band is released as a renamed derived column, which the kit scorecard does not recognise as a QI; our per-person k over every released QI is authoritative"},
        {"id": "lab-test-name-qi", "status": "open",
         "note": "D33 branch A taken: lab_results.test_name is a QI (ladder full, CRP vs other, withheld), counted in "
                 "per-person k if released. Measured on the real kit with the search plan (#106; below-k share before "
                 "suppression / suppression share needed, cap 0.10): full 0.536 / 0.663, CRP vs other 0.372 / 0.507, "
                 "withheld 0.043 / 0.099. The search withholds it and the cap holds, so the justified non-QI "
                 "fallback is not taken; H-U7 0.983 either way (it selects CRP by test_code)"},
        {"id": "attribute-lift-bound", "status": "open",
         "note": f"D64: attribute-inference lift (attacker accuracy / base-rate accuracy) at most {MAX_LIFT} for "
                 f"icd10_primary and los_minutes, enforced by the search on the released visits (search log, final "
                 f"step); a plan over it is refused. icd10 stays at 3 characters (chapter level fails H-U4); "
                 f"los_minutes is binned at least {LOS_BIN_MIN} minutes wide. Residual against the stated attacker: "
                 f"each attribute-inference-redteam-<column> entry over its -baseline entry"},
        {"id": "lab-test-code-identity", "status": "open",
         "note": "test_code is released exact for H-U7 and is not a detector QI, yet carries the same test identity "
                 "as test_name: a person's set of lab tests could single them out to someone who knows their test "
                 "history"},
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
        {"table": "ed_visits", "column": "sex", "derived": "sex",
         "note": "conditional QI: withheld in the hand plan (no check needs it); counted if a plan releases it"},
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
        {"table": "lab_results", "column": "test_name", "derived": "test_name",
         "join_via": ["ed_visits", "visit_id"],
         "note": "D33: the detector classifies it as a QI; counted as a join-derived QI if released"},
    ),
    risk_vector=("qi_k_shortfall", "qi_unique_rate", "join_derived_qi", "direct_identifier_leak", "attribute_inference"),
    sacrifices=(
        {"check": "H-U4", "floor_score": 0.6, "reason": "municipality grouping to top-N to reach k", "via": [{"table": "ed_visits", "column": "municipality"}]},
        {"check": "H-U6", "floor_score": 0.6, "reason": "coarser age band to reach k", "via": [{"table": "ed_visits", "column": "date_of_birth"}]},
        {"check": "H-U8", "floor_score": 0.6, "reason": "coarser arrival time to reach k", "via": [{"table": "ed_visits", "column": "arrival_ts"}]},
    ),
    rung_sacrifices=(
        {"check": "H-U8", "table": "ed_visits", "column": "arrival_ts", "from": "ts.month_hour",
         "to": "ts.hour_of_day",
         "reason": "hour of day only (drops all date meaning): taken only if per-person k at month+hour needs more "
                   "suppression than the budget and H-U8 still passes at hour of day"},
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
    alt_floor_conditions={("ed_visits", "patient_hetu"): {"check": "H-U6", "outcome": "fail_without"}},
    param_minimums={("ed_visits", "municipality"): {"rung": "geo.topn", "param": "n", "min": 8},
                    # D64 (#157): 30-minute stay bands, the width that brings the los_minutes lift under the bound
                    ("ed_visits", "los_minutes"): {"rung": "num.bin", "param": "width", "min": LOS_BIN_MIN}},
    attribute_lift=ATTRIBUTE_LIFT,
)


def hand_plan() -> list:
    return [dict(e, params=dict(e["params"])) for e in _PLAN]
