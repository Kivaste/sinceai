"""CS-S1 policy and hand-picked plan. Spec #1, per-column table."""
from __future__ import annotations

from ._build import build, withheld_table
from .model import ScenarioPolicy

REL = {"label": "RECORD_KEY"}
C = "conversations"
T = "turns"


def _r(t, c, fam, floor, direct, freason, hrung=None, hparams=None, hreason=None):
    return (t, c, fam, floor, direct, freason, hrung or floor, hparams or {}, hreason or freason)


_ROWS = [
    _r(C, "conversation_id", "identifier", "pseudonym", False, "release-scope pseudonym, identical in turns (linkage)", "pseudonym", REL),
    _r(C, "customer_id", "identifier", "withheld", True, "links to the withheld customers table"),
    _r(C, "agent_id", "identifier", "pseudonym", False, "agent-quality purpose; no required check", "pseudonym", REL),
    _r(C, "agent_name", "identifier", "withheld", True, "staff direct identifier"),
    _r(C, "channel", "categorical", "exact", False, "no required check"),
    _r(C, "language", "categorical", "exact", False, "no required check"),
    _r(C, "started_ts", "timestamp", "hour", False, "scenario target: timestamps rounded to the hour"),
    _r(C, "intent", "categorical", "exact", False, "CS-U1, CS-U3, CS-U4"),
    _r(C, "sentiment", "categorical", "exact", False, "no required check"),
    _r(C, "csat", "categorical", "exact", False, "no required check"),
    _r(C, "resolved", "categorical", "exact", False, "no required check"),
    _r(C, "handle_time_s", "numeric", "exact", False, "CS-U4"),
    _r(C, "n_turns", "numeric", "exact", False, "no required check"),
    _r(C, "split", "categorical", "exact", False, "CS-U1 reads it from the protected table; dropping it broke CS-U1 under B2"),
    _r(C, "agent_note", "text", "withheld", False, "free text, no check needs it"),
    _r(T, "turn_id", "categorical", "exact", False,
       "kept as-is iff check turn-id-synthetic confirms a synthetic record key (CS-U5 matches by turn_id)",
       "exact", {"requires_check": "turn-id-synthetic", "fallback_rung": "id.pseudonym"},
       "kept as-is only if turn-id-synthetic passes; else release-scope pseudonym with a lineage adapter"),
    _r(T, "conversation_id", "identifier", "pseudonym", False, "release-scope pseudonym, identical in conversations", "pseudonym", REL),
    _r(T, "seq", "numeric", "exact", False, "CS-U1 orders by seq"),
    _r(T, "speaker", "categorical", "exact", False, "CS-U1"),
    _r(T, "ts", "timestamp", "hour", False, "scenario target: hour"),
    _r(T, "text", "text", "redacted", False, "CS-U1, CS-U5; placeholders scoped per conversation"),
]
_ROWS += withheld_table("customers", [
    ("customer_id", "identifier"), ("customer_number", "identifier"), ("full_name", "identifier"),
    ("hetu", "identifier"), ("street_address", "identifier"), ("postcode", "geo"), ("city", "geo"),
    ("email", "identifier"), ("phone", "identifier"), ("preferred_language", "categorical"),
    ("customer_since", "timestamp"), ("products", "categorical"), ("contract_number", "identifier"),
    ("payment_method", "categorical"), ("iban", "identifier"), ("marketing_consent", "categorical"),
    ("payment_default_flag", "categorical"), ("accessibility_needs", "categorical"),
], "table withheld: no purpose check needs it")

FLOORS, DIRECT, _PLAN = build(_ROWS)
# every customers column is a person-level field; withheld table. Direct identifiers among them:
DIRECT = tuple(sorted(set(DIRECT) | {("customers", c) for c in (
    "customer_id", "customer_number", "full_name", "hetu", "street_address", "email", "phone",
    "contract_number", "iban")}))

POLICY = ScenarioPolicy(
    scenario="CS-S1",
    dataset="customer_service",
    purpose_checks=("CS-U1", "CS-U3", "CS-U4", "CS-U5"),
    privacy_targets=(
        {"id": "text-recall", "kind": "text_recall", "min": 0.98,
         "labels": ["NATIONAL_ID", "PAYMENT_CARD", "IBAN", "SECRET"]},
        {"id": "no-health-in-text", "kind": "health_in_text", "max_hits": 0},
        {"id": "timestamps-hour", "kind": "timestamp_floor", "rung": "ts.hour"},
    ),
    floors=FLOORS,
    direct_identifiers=DIRECT,
    qi=(),
    risk_vector=("text_recall_shortfall", "health_in_text", "direct_identifier_leak", "pseudonym_linkage"),
    sacrifices=(
        {"check": "CS-U5", "floor_score": 0.8, "reason": "vocabulary removed by redaction of identifying phrases",
         "via": [{"table": "turns", "column": "text"}]},
    ),
    joint_qi_moves=(),
    linked=((("conversations", "conversation_id"), ("turns", "conversation_id")),),
    param_minimums={},
    alt_floors={("turns", "turn_id"): "id.pseudonym"},
)


def hand_plan() -> list:
    return [dict(e, params=dict(e["params"])) for e in _PLAN]


def turn_id_fallback_plan(plan: list) -> list:
    """Plan for when check turn-id-synthetic fails: turns.turn_id becomes a release-scope pseudonym."""
    out = []
    for e in plan:
        e = dict(e, params=dict(e["params"]))
        if (e["table"], e["column"]) == ("turns", "turn_id"):
            e.update(rung="id.pseudonym", floor="id.pseudonym", params={"label": "RECORD_KEY"},
                     reason="turn-id-synthetic failed: release-scope pseudonym; lineage adapter restores scoring IDs")
        out.append(e)
    return out
