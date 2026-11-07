"""CS-S1: plan selection (turn_id decision), controller gazetteer, redactor binding, transform."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from pets_release.checks.turn_id.synthetic import NAME as TURN_ID_CHECK
from pets_release.checks.turn_id.synthetic import assess
from pets_release.ladders import apply
from pets_release.policy import get_policy, hand_plan, validate_plan
from pets_release.policy.cs_s1 import turn_id_fallback_plan
from pets_release.redactor import PRIORITY_CUE, Candidate, StructuredPass, Turn, lexicon, redact_conversation

SCENARIO = "CS-S1"
TURN_KEY = ("turns", "turn_id")


@dataclass(frozen=True)
class TurnIdDecision:
    kept: bool
    assessment: dict  # {check, status: pass|fail, n, hits: {label: rows}}; counts only
    justification: dict  # manifest fieldJustifications entry (02's shape)


@dataclass(frozen=True)
class Prepared:
    plan: list
    tables: dict
    spans: list
    turn_id: TurnIdDecision
    gate_context: dict
    gazetteer: object


def identifiers(policy, turn_id_kept: bool) -> list[dict]:
    """Source identifier columns for producer checks: policy direct identifiers plus every
    identifier-family column; ``turns.turn_id`` only when it is not kept as-is."""
    keys = set(policy.direct_identifiers)
    keys |= {k for k, f in policy.floors.items() if f.family == "identifier"}
    if not turn_id_kept:
        keys.add(TURN_KEY)
    else:
        keys.discard(TURN_KEY)
    return [{"table": t, "column": c} for t, c in sorted(keys)]


def build_gazetteer(source: dict) -> lexicon.Gazetteer:
    """Controller gazetteer from the source tables, in memory: customer and agent names, cities,
    streets, and the parties (customer, agent) of each conversation."""
    cust = source["customers"]
    conv = source["conversations"]
    name_of = dict(zip(cust["customer_id"], cust["full_name"]))
    parties: dict[str, list[str]] = {}
    for cid, cust_id, agent in zip(conv["conversation_id"], conv["customer_id"], conv["agent_name"]):
        parties[cid] = [n for n in (name_of.get(cust_id, ""), agent) if n]
    return lexicon.Gazetteer.from_tables(
        full_names=sorted(set(cust["full_name"]) | set(conv["agent_name"])),
        cities=sorted(set(cust["city"])),
        streets=sorted(set(cust["street_address"])),
        parties=parties,
    )


# Controller identifier columns whose exact values are redacted wherever they occur in turns.
CONTROLLER_VALUES = (
    ("customers", "customer_id", "ACCOUNT_NUMBER"),
    ("customers", "customer_number", "ACCOUNT_NUMBER"),
    ("customers", "contract_number", "ACCOUNT_NUMBER"),
    ("customers", "hetu", "NATIONAL_ID"),
    ("customers", "iban", "IBAN"),
    ("customers", "email", "EMAIL"),
    ("customers", "phone", "PHONE"),
)
_TOKEN = re.compile(r"[^\W_](?:[\w.@+-]*[^\W_])?")
MIN_VALUE = 5


class ControllerValuesPass:
    """Exact controller identifier values (from the source tables, in memory) in the text.

    Single-token values match as whole tokens anywhere (case-folded); values with internal
    whitespace match, whitespace-tolerant, in the conversations of their own customer
    (``own``: conversation id -> {label: values}). Below the validators' priority, so a validated
    hit keeps its span; it fills gaps such as letter-prefixed customer numbers.
    """

    name = "controller-values"

    def __init__(self, values: dict, own: dict | None = None):
        self._single = {}
        for label in sorted(values):
            for v in values[label]:
                v = str(v).strip()
                if len(v) >= MIN_VALUE and _TOKEN.fullmatch(v):
                    self._single.setdefault(v.casefold(), label)
        self._own = {}
        for cid, by_label in (own or {}).items():
            pats = []
            for label in sorted(by_label):
                for v in sorted(by_label[label]):
                    parts = str(v).split()
                    if len(parts) > 1 and len("".join(parts)) >= MIN_VALUE:
                        pats.append((re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, parts)) + r"(?!\w)", re.IGNORECASE), label))
            if pats:
                self._own[cid] = pats
        self.labels = frozenset(lab for _, _, lab in CONTROLLER_VALUES)

    def run(self, view):
        out = []
        for i, t in enumerate(view.turns):
            for m in _TOKEN.finditer(t.text):
                label = self._single.get(m.group(0).casefold())
                if label:
                    out.append(Candidate(i, m.start(), m.end(), label, PRIORITY_CUE, None, self.name))
            for pat, label in self._own.get(view.conversation_id, ()):
                for m in pat.finditer(t.text):
                    out.append(Candidate(i, m.start(), m.end(), label, PRIORITY_CUE, None, self.name))
        return out


def controller_values_pass(source: dict) -> ControllerValuesPass:
    values: dict = {}
    for t, c, label in CONTROLLER_VALUES:
        if t in source and c in source[t].columns:
            values.setdefault(label, set()).update(v for v in source[t][c] if v)
    own: dict = {}
    cust = source.get("customers")
    conv = source.get("conversations")
    if cust is not None and conv is not None:
        rows = {r["customer_id"]: r for r in cust.to_dict("records")}
        for cid, cust_id in zip(conv["conversation_id"], conv["customer_id"]):
            r = rows.get(cust_id)
            if r is None:
                continue
            by: dict = {}
            for t, c, label in CONTROLLER_VALUES:
                if t == "customers" and r.get(c):
                    by.setdefault(label, set()).add(r[c])
            own[cid] = by
    return ControllerValuesPass(values, own)


def _seq_key(v: str):
    s = str(v).strip()
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def _redactor(gazetteer, values_pass, spans_out: list):
    passes = [StructuredPass(), values_pass, *lexicon.passes(gazetteer)]

    def redact(table: str, column: str, frame: pd.DataFrame, params: dict) -> pd.Series:
        if (table, column) != ("turns", "text"):
            raise ValueError("CS-S1 redactor applies to turns.text only")
        out = pd.Series([""] * len(frame), index=frame.index, dtype=object)
        work = pd.DataFrame({"conv": frame["conversation_id"].astype(str), "tid": frame["turn_id"].astype(str),
                             "seq": frame["seq"].astype(str), "speaker": frame["speaker"].astype(str),
                             "text": frame["text"].fillna("").astype(str), "pos": range(len(frame))},
                            index=frame.index)
        for cid in sorted(work["conv"].unique()):
            g = work[work["conv"] == cid]
            order = sorted(range(len(g)), key=lambda i: (_seq_key(g["seq"].iloc[i]), g["pos"].iloc[i]))
            g = g.iloc[order]
            turns = [Turn(turn_id=t, text=x, speaker=sp, seq=sq)
                     for t, x, sp, sq in zip(g["tid"], g["text"], g["speaker"], g["seq"])]
            red = redact_conversation(cid, turns, passes=passes)
            spans_out.extend(red.spans)
            for idx, tid in zip(g.index, g["tid"]):
                out.at[idx] = red.texts[tid]
        return out

    return redact


def _decide_turn_id(source: dict, policy) -> TurnIdDecision:
    turns = source["turns"]
    hits = assess(turns["turn_id"], turns["conversation_id"], source, identifiers(policy, turn_id_kept=True))
    status = "fail" if hits else "pass"
    assessment = {"check": TURN_ID_CHECK, "status": status, "n": len(turns), "hits": hits}
    if status == "pass":
        just = {"rung": "keep", "floor": "keep", "decision": "released",
                "reason": f"kept as-is: check {TURN_ID_CHECK} passed on the candidate ({len(turns)} turns, 0 hits): "
                          "a synthetic record key with no person or conversation information; CS-U5 matches by turn_id"}
    else:
        labels = ", ".join(f"{k} {v}" for k, v in hits.items())
        just = {"rung": "id.pseudonym", "floor": "id.pseudonym", "decision": "released",
                "reason": f"release-scope pseudonym: check {TURN_ID_CHECK} failed on the candidate ({labels}); "
                          "CS-U5 reported twice: unmodified kit score and row-map-lineage adapted score"}
    just = {"table": "turns", "column": "turn_id", "outputColumn": "turn_id", "source": "hand", **just}
    return TurnIdDecision(kept=status == "pass", assessment=assessment, justification=dict(sorted(just.items())))


def prepare(source: dict, keys, plan: list | None = None) -> Prepared:
    """CS-S1 release tables from the customer_service source tables. Pure apart from computation:
    no I/O; the gazetteer and mappings stay in memory."""
    policy = get_policy(SCENARIO)
    decision = _decide_turn_id(source, policy)
    plan = hand_plan(SCENARIO) if plan is None else [dict(e, params=dict(e["params"])) for e in plan]
    if not decision.kept:
        plan = turn_id_fallback_plan(plan)
    validate_plan(plan, policy)
    gaz = build_gazetteer(source)
    spans: list = []
    tables = apply(plan, source, keys, redactor=_redactor(gaz, controller_values_pass(source), spans))
    spans = sorted(spans, key=lambda s: (s["record_id"], s["start"], s["end"], s["label"]))
    ctx = {"source": source, "identifiers": identifiers(policy, decision.kept)}
    return Prepared(plan=plan, tables=tables, spans=spans, turn_id=decision, gate_context=ctx, gazetteer=gaz)
