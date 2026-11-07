"""CS-S1 real-kit blocker (ticket 23 chain): the redactor is at least as broad as the gate's username cue rule.

Rule: a plain word directly after a username cue (no copula) that the gate counts as the value (the gate's own
``_value_ok("username", ...)``: handle-shaped, 3-64 chars, not prose, not a stop word) is redacted as USERNAME.

Rows (trigger -> result):
  username cue + plain non-prose word, no copula  -> raw text fails rescan/text.usernames; redacted text passes
  username cue + prose word ("username reset")    -> not redacted (the gate does not count it either)
Every row is hand-made synthetic text; the production redactor and the production gate runner are used.
"""
from __future__ import annotations

import csv

import pytest

from pets_release.checks import all_checks, run_checks
from pets_release.redactor import Turn, redact_conversation

CONTRACT = {
    "files": {"turns.csv": {"required": ["turn_id", "conversation_id", "seq", "text"], "columns": {
        "turn_id": {"form": "^T[0-9]+$", "params": {}},
        "conversation_id": {"form": "^C[0-9]+$", "params": {}},
        "seq": {"form": "integer", "params": {}},
        "speaker": {"form": "enum", "params": {"values": ["customer", "agent"]}},
        "text": {"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}}}}},
    "qi": [], "tokens": [], "healthInTextRequired": True,
}
USER_CHECKS = ("rescan.usernames", "text.usernames")


def _gate(folder, text):
    folder.mkdir(parents=True)
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["turn_id", "conversation_id", "seq", "speaker", "text"])
        w.writerow(["T1", "C1", "1", "customer", text])
    checks = [c for c in all_checks() if c.name in USER_CHECKS]
    return {r.check: r for r in run_checks(folder, CONTRACT, {"phase": "gate"}, checks=checks).records}


def _redact(text):
    return redact_conversation("C1", [Turn(turn_id="T1", text=text, speaker="customer", seq="1")]).texts["T1"]


@pytest.mark.parametrize(("text", "value"), [
    ("my username jsmithx does not work", "jsmithx"),
    ("login maijamaa ei toimi", "maijamaa"),
    ("username kotikissa", "kotikissa"),
    ("login failed again", "failed"),  # a gate false positive; over-redacted on purpose so the gate passes
])
def test_plain_word_after_username_cue_is_redacted(tmp_path, text, value):
    raw = _gate(tmp_path / "raw", text)
    assert any(r.status == "fail" for r in raw.values()), {k: r.status for k, r in raw.items()}
    red = _redact(text)
    assert value not in red and "[USERNAME_" in red
    after = _gate(tmp_path / "red", red)
    assert all(r.status == "pass" for r in after.values()), {k: (r.status, r.hits) for k, r in after.items()}


@pytest.mark.parametrize("text", ["my username reset did not arrive", "the username field is empty"])
def test_prose_after_username_cue_is_kept(text):
    assert "[USERNAME_" not in _redact(text)
