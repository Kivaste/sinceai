"""#53 round 5, redactor side: the redactor redacts the cue + value shapes the gate counts, so a CS-S1
release stays passable after the gate fixes. Redactor seam (turns in -> spans/placeholders out); the
redacted text is then scanned by the production gate functions. Synthetic phrases only.

Failure rows (trigger -> result before the change):
  cue + copula + clock time/date masked by the denylist ("wifi is 12:30")  -> kept (scan stopped at the mask)
  cue + hedge glued to its value ("password probably:kissakala")           -> kept (one non-value token)
  cue + other words + a later copula + value ("password for the router is
  kissakala")                                                              -> kept (only credential shapes
                                                                              counted after other words)
"""

from __future__ import annotations

import pytest

from pets_release.checks.cells import _validators as V
from pets_release.checks.text import _detectors as D
from pets_release.checks.text import _normalise as N
from pets_release.redactor import StructuredPass, Turn, redact_conversation


def labelled(text):
    ts = [Turn(turn_id="c1-t0", text=text, speaker="customer", seq="0")]
    r = redact_conversation("c1", ts, passes=[StructuredPass()])
    return [(text[s["start"]:s["end"]], s["label"]) for s in r.spans], r.texts["c1-t0"]


def gate_hits(redacted):
    view = N.view(redacted, "digit")
    return {
        "rescan.secrets": V.secrets(redacted)[0],
        "rescan.usernames": V.usernames(redacted)[0],
        "text.secrets": len(D.secrets(view)),
        "text.usernames": len(D.usernames(view)),
    }


CASES = [
    ("wifi is 12:30 tomorrow", "12:30", "SECRET"),
    ("wlan on 12.03.2021 huomenna", "12.03.2021", "SECRET"),
    ("password is 12:30", "12:30", "SECRET"),
    ("username is 12:30", "12:30", "USERNAME"),
    ("password reset is 12:30", "12:30", "SECRET"),
    ("password probably:kissakala", "kissakala", "SECRET"),
    ("salasana nyt:kissakala", "kissakala", "SECRET"),
    ("password for the router still:kissakala", "kissakala", "SECRET"),
    ("password for the router still: kissakala", "kissakala", "SECRET"),
    ("password for the router is kissakala", "kissakala", "SECRET"),
    ("password for the router: kissakala", "kissakala", "SECRET"),
    ("username probably:mattikoski", "mattikoski", "USERNAME"),
    ("username for the shop still:mattikoski", "mattikoski", "USERNAME"),
]


@pytest.mark.parametrize("text,value,label", CASES)
def test_gate_counted_value_is_redacted(text, value, label):
    spans, red = labelled(text)
    assert (value, label) in spans
    assert gate_hits(red) == {"rescan.secrets": 0, "rescan.usernames": 0, "text.secrets": 0, "text.usernames": 0}


# not values: nothing is redacted and the gate finds nothing
@pytest.mark.parametrize("text", ["wifi is slow at 12:30", "password reset at 12:30 tomorrow",
                                  "username probably:unknown", "password for the router is broken"])
def test_prose_stays(text):
    spans, red = labelled(text)
    assert spans == []
    assert gate_hits(red) == {"rescan.secrets": 0, "rescan.usernames": 0, "text.secrets": 0, "text.usernames": 0}
