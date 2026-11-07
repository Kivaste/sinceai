"""Must-fix #54 round 5 (Sol r4 HIGH): a numeric secret later in the clause after a re-armed plain word.

Rule: after '<password cue> <copula> <plain word>', a digit-only credential later in the same clause is the
value too (the gate counts it), so both are redacted; dates and clock times are not credentials.

Rows (trigger -> result):
  cue + copula + short-stem-prefix word + two words + 9-10 digits -> raw text fails the secret checks;
                                                                     redacted text passes every secret check
  same with a date / clock time instead of the digits             -> not taken as a second SECRET
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
SECRET_CHECKS = ("rescan.secrets", "text.secrets")

CASES = [
    ("the password is pinkki blue house 4821357902", "4821357902"),
    ("salasana on pinkki sininen talo 482135790", "482135790"),
    ("my password is pinja green tree 4821357902 thanks", "4821357902"),
]


def _gate(tmp_path, text):
    folder = tmp_path / "rel"
    folder.mkdir(parents=True)
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["turn_id", "conversation_id", "seq", "speaker", "text"])
        w.writerow(["T1", "C1", "1", "customer", text])
    checks = [c for c in all_checks() if c.name in SECRET_CHECKS]
    return {r.check: r for r in run_checks(folder, CONTRACT, {"phase": "gate"}, checks=checks).records}


def _redact(text):
    return redact_conversation("C1", [Turn(turn_id="T1", text=text, speaker="customer", seq="1")]).texts["T1"]


@pytest.mark.parametrize(("text", "secret"), CASES)
def test_numeric_secret_after_rearmed_plain_word_is_redacted(tmp_path, text, secret):
    raw = _gate(tmp_path / "raw", text)
    assert any(r.status == "fail" for r in raw.values()), {k: r.status for k, r in raw.items()}  # the gate sees it
    red = _redact(text)
    assert secret not in red
    after = _gate(tmp_path / "red", red)
    assert all(r.status == "pass" for r in after.values()), {k: (r.status, r.hits) for k, r in after.items()}


@pytest.mark.parametrize("tail", ["12.03.2024", "14:30"])
def test_date_or_time_later_in_clause_is_not_taken_as_the_secret(tail):
    red = _redact(f"the password is pinkki blue house {tail}")
    assert red.count("[SECRET_") == 1  # only the plain word; a date/time may be a DATE span, never the secret
