"""Sol r1 Spec (2): held-out SECRET recall must reach the spec floor. Rule: a misspelled strong password cue
(within 1 edit, 2 for cues of 10+ letters; same first letter) followed by a copula (+ hedges) and a
credential-shaped value is a SECRET cue. Only credential-shaped values count after a misspelled cue (never a
plain word), and words that are not misspellings of a password cue ("passport") are no cue.
Redactor seam (turns in -> spans out). Synthetic phrases only.

Rows (trigger -> result before the change):
  misspelled password cue + copula + credential  -> kept (no cue)
"""
from __future__ import annotations

import pytest

from pets_release.redactor import StructuredPass, Turn, redact_conversation


def labelled(text):
    r = redact_conversation("c1", [Turn(turn_id="t0", text=text, speaker="customer", seq="0")],
                            passes=[StructuredPass()])
    return [(text[s["start"]:s["end"]], s["label"]) for s in r.spans]


@pytest.mark.parametrize("text,value", [
    ("my paasword is Talvi2031! thanks", "Talvi2031!"),
    ("my passwrd is Kissa77x now", "Kissa77x"),
    ("Salasanna on KesaLoma24 kiitos", "KesaLoma24"),
    ("Salsananai on KesaLoma24 kiitos", "KesaLoma24"),
    ("lösenrdet är Sommar2024 tack", "Sommar2024"),
])
def test_misspelled_password_cue_then_credential_is_redacted(text, value):
    assert (value, "SECRET") in labelled(text)


@pytest.mark.parametrize("text", [
    "my paasword is broken again",        # plain word after a misspelled cue: never a value
    "my passport is AB1234567 thanks",    # not a misspelling of a password cue
    "my paasword reset Talvi2031 failed",  # no copula
])
def test_no_secret_without_misspelled_cue_copula_and_credential(text):
    assert not [v for v, lab in labelled(text) if lab == "SECRET"]
