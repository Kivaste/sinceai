"""Must-fix #92: identifiers split across adjacent turns of one conversation.

Rule: after redaction, the gate's own text checks (same detectors, same N-turn stitching) find no
identifier in the redacted conversation. Every fragment of a split identifier is redacted; for a
cue-introduced value (SECRET, USERNAME, ACCOUNT_NUMBER) a fragment that holds only the cue words
is kept.

Failure rows (trigger -> result):
  cue ends turn k, value is turn k+1           -> value turn redacted, cue turn untouched, gate clean
  value split over turns k, k+1 (no validator) -> both fragments redacted, one placeholder number
  split over a backchannel turn (k, k+2)       -> both fragments redacted, backchannel untouched
  no gate hit in the conversation              -> output identical to the per-turn pipeline
  single-turn gate hit in an untouched turn    -> left to the passes (not widened here)
  gate hit that redaction cannot remove        -> ValueError (fail closed), never a silent leak

Every row is hand-made synthetic (textbook test identifiers, invented words); never kit rows.
Checks run through the production redactor and the production gate runner.
"""
from __future__ import annotations

import csv

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.redactor import Turn, redact_conversation
from pets_release.redactor import cross_turn

TURN_COLUMNS = ["turn_id", "conversation_id", "seq", "speaker", "text"]

CONTRACT = {
    "files": {
        "turns.csv": {
            "required": ["turn_id", "conversation_id", "seq", "text"],
            "columns": {
                "turn_id": {"form": "^T[0-9]+$", "params": {}},
                "conversation_id": {"form": "^C[0-9]+$", "params": {}},
                "seq": {"form": "integer", "params": {}},
                "speaker": {"form": "enum", "params": {"values": ["customer", "agent"]}},
                "text": {"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}},
            },
        }
    },
    "qi": [],
    "tokens": [],
    "healthInTextRequired": True,
}

# conversation -> the values that must not survive anywhere in the redacted turns
SPLIT_CUE = {
    "cue-then-secret": ([("agent", "Please confirm the password is"), ("customer", "Zq7!kp9x")], ["Zq7!kp9x"]),
    "colon-then-secret": ([("customer", "my password:"), ("customer", "Tr0ub4dor&3")], ["Tr0ub4dor&3"]),
    "copula-then-word": ([("customer", "the salasana on"), ("customer", "kissakala")], ["kissakala"]),
    "cue-then-username": ([("customer", "my username is"), ("customer", "jdoe_42")], ["jdoe_42"]),
}


def _turns(conv):
    return [Turn(turn_id=f"T{i + 1}", text=t, speaker=s, seq=str(i + 1)) for i, (s, t) in enumerate(conv)]


def _gate(tmp_path, texts):
    """Write the redacted turns as a release and run every text.* gate check (gate phase)."""
    folder = tmp_path / "release"
    folder.mkdir(parents=True)
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(TURN_COLUMNS)
        for i, (speaker, text) in enumerate(texts):
            w.writerow([f"T{i + 1}", "C1", str(i + 1), speaker, text])
    checks = [c for c in all_checks() if c.name.startswith("text.") and c.name != "text.health"]
    assert len(checks) >= 13
    result = run_checks(folder, CONTRACT, {"phase": "gate"}, checks=checks)
    recs = [r.to_dict() for r in result.records]
    assert len(recs) == len(checks)
    return {r["check"]: r for r in recs}


def _hits(records):
    return {name: sum(v["count"] for v in r["violations"]) for name, r in records.items() if r["violations"]}


def _statuses(records):
    return {r["status"] for r in records.values()}


@pytest.mark.parametrize("case", sorted(SPLIT_CUE))
def test_cue_split_is_clean_after_redaction(tmp_path, case):
    conv, secrets = SPLIT_CUE[case]
    # precondition: the gate flags the unredacted conversation across the two turns
    assert _hits(_gate(tmp_path / "raw", conv))
    turns = _turns(conv)
    red = redact_conversation("C1", turns)
    out = [(s, red.texts[t.turn_id]) for (s, _), t in zip(conv, turns)]
    for value in secrets:
        assert all(value not in text for _, text in out)
    assert out[0][1] == conv[0][1]  # the cue turn holds no value: kept as is
    records = _gate(tmp_path / "red", out)
    assert _hits(records) == {}
    assert _statuses(records) == {"pass"}


def test_split_value_both_fragments_redacted_with_one_placeholder(tmp_path):
    # no per-turn pass at all: the cross-turn step alone must redact both fragments of the card
    conv = [("customer", "card 4111 1111"), ("customer", "1111 1111 thanks")]
    assert _hits(_gate(tmp_path / "raw", conv)) == {"text.payment-cards": 1}
    turns = _turns(conv)
    red = redact_conversation("C1", turns, passes=[])
    a, b = red.texts["T1"], red.texts["T2"]
    assert a == "card [PAYMENT_CARD_1]" and b == "[PAYMENT_CARD_1] thanks"
    assert {s["label"] for s in red.spans} == {"PAYMENT_CARD"}
    assert _hits(_gate(tmp_path / "red", [("customer", a), ("customer", b)])) == {}


def test_split_over_backchannel_turn(tmp_path):
    conv = [("customer", "it is 4111 1111"), ("agent", "ok"), ("customer", "1111 1111")]
    assert _hits(_gate(tmp_path / "raw", conv)) == {"text.payment-cards": 1}
    red = redact_conversation("C1", _turns(conv), passes=[])
    assert red.texts["T2"] == "ok"
    assert "1111" not in red.texts["T1"] + red.texts["T3"]
    assert _hits(_gate(tmp_path / "red", [(s, red.texts[f"T{i + 1}"]) for i, (s, _) in enumerate(conv)])) == {}


def test_no_gate_hit_leaves_pipeline_output_unchanged():
    conv = [("customer", "hello, my order is late"), ("agent", "sorry to hear that")]
    turns = _turns(conv)
    red = redact_conversation("C1", turns)
    assert red.texts == {"T1": conv[0][1], "T2": conv[1][1]}
    assert cross_turn.PASS_NAME not in red.passes_run


def test_single_turn_gate_hit_in_untouched_turn_is_not_widened():
    # within one turn the passes own precision: this step only acts on hits that span turns
    conv = [("customer", "the password was last changed in 2023"), ("agent", "thanks")]
    assert cross_turn.gate_hits([t for _, t in conv])  # the gate is broader here, by design
    red = redact_conversation("C1", _turns(conv))
    assert red.texts == {"T1": conv[0][1], "T2": conv[1][1]}
    assert cross_turn.PASS_NAME not in red.passes_run


def test_unremovable_hit_fails_closed(monkeypatch):
    # a gate hit that redaction cannot remove (it reappears every round) is an error, never a leak
    def stuck(texts):
        return [("SECRET", [(0, 0, len(texts[0])), (1, 0, len(texts[1]))])]

    monkeypatch.setattr(cross_turn, "gate_hits", stuck)
    with pytest.raises(ValueError, match="cross-turn"):
        redact_conversation("C1", _turns([("customer", "abc"), ("customer", "def")]))


def test_join_logic_is_the_gates(monkeypatch):
    # shared, not duplicated: the redactor stitches with the gate scanner's own function; with it
    # stubbed to find nothing the split secret survives, so the redactor has no join logic of its own
    from pets_release.checks.text import _scan

    calls = []
    monkeypatch.setattr(_scan, "conversation_hits", lambda conv, det, view: calls.append(view) or [])
    conv, (value,) = SPLIT_CUE["cue-then-secret"]
    red = redact_conversation("C1", _turns(conv))
    assert calls and value in red.texts["T2"]
