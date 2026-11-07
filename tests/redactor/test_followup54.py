"""Must-fix #54 round 2: the redactor's SECRET/USERNAME/PHONE coverage follows the gate's rule shape.

Rule added: after a credential cue (general fi/sv/en vocabulary, the gate's cue classes) the value token is
redacted when it is digits (3+; longer than a PIN after a password-type cue), credential-shaped, or an
alphabetic non-prose word after a copula that ends its clause, where a following identifier token (digit, '@',
masked literal) also ends it; bare @handles are
usernames; international phones written with + (8-15 digits) or 00 (10-15 digits).
Not added (the labelled train split has 0 gold spans for these gate shapes): mid-clause alphabetic words
after 'wifi is', and alphabetic words after a username cue without a copula.

Failure rows (trigger -> result before the change):
  password cue + copula + alpha + identifier token  -> missed (alpha needed punctuation/end of turn)
  password cue + 3 digits, or > 8 digits            -> missed (SECRET digits were 4-8 only)
  pwd / wi-fi / OTP / verification-type codes / cvv -> missed (cue not in the vocabulary)
  tunnukseni / userid / anvandar-id cues, @handle   -> missed
  +CC phone (non-FI, 8-15 digits), 00CC (10-15)     -> missed
  phone on its own line after a trailing dash       -> glued into the number above
All values are synthetic.
"""

from __future__ import annotations

import pytest

from pets_release.checks.cells import _validators as V
from pets_release.checks.text import _detectors as D
from pets_release.checks.text import _normalise as N
from pets_release.redactor import StructuredPass, Turn, redact_conversation


def conv(*turns, cid="c1"):
    ts = [Turn(turn_id=f"{cid}-t{i}", text=t, speaker="customer", seq=str(i)) for i, t in enumerate(turns)]
    return redact_conversation(cid, ts, passes=[StructuredPass()])


def labelled(text):
    r = conv(text)
    return [(text[s["start"]:s["end"]], s["label"]) for s in r.spans], r.texts["c1-t0"]


def gate_hits(redacted):
    """The production gate checks (cell rescan and text detectors) on one redacted row."""
    view = N.view(redacted, "digit")
    return {
        "rescan.secrets": V.secrets(redacted)[0],
        "rescan.usernames": V.usernames(redacted)[0],
        "rescan.phones": V.phones(redacted)[0],
        "text.secrets": len(D.secrets(view)),
        "text.usernames": len(D.usernames(view)),
        "text.phones": len(D.phones(view)),
    }


POSITIVE = [
    ("my wifi password is sunflower", "sunflower", "SECRET"),
    ("wlan salasana on kotiverkko.", "kotiverkko", "SECRET"),
    ("salasana on lumiukko 040 123 4567", "lumiukko", "SECRET"),
    ("salasana on lumiukko maija@example.com", "lumiukko", "SECRET"),
    ("salasana 482 kiitos", "482", "SECRET"),
    ("lösenordet är 4821357902 tack", "4821357902", "SECRET"),
    ("pwd: Xr7kq2Lm", "Xr7kq2Lm", "SECRET"),
    ("wi-fi on Xr7kq2Lm", "Xr7kq2Lm", "SECRET"),
    ("wpa2 key Xr7kq2Lm", "Xr7kq2Lm", "SECRET"),
    ("vahvistuskoodi on 482913", "482913", "SECRET"),
    ("the verification code is 482913", "482913", "SECRET"),
    ("OTP 482913 please", "482913", "SECRET"),
    ("sms code: 4829", "4829", "SECRET"),
    ("engångskod 482913", "482913", "SECRET"),
    ("cvv 123", "123", "SECRET"),
    ("tunnukseni on maijamaa", "maijamaa", "USERNAME"),
    ("tunnuksella maijam85 ei pääse", "maijam85", "USERNAME"),
    ("userid: mmeikalainen", "mmeikalainen", "USERNAME"),
    ("användar-id är maijam85", "maijam85", "USERNAME"),
    ("seuraa meitä @maija_m kiitos", "@maija_m", "USERNAME"),
    ("soita +44 20 7946 0958 kiitos", "+44 20 7946 0958", "PHONE"),
    ("soita 0044 20 7946 0958 kiitos", "0044 20 7946 0958", "PHONE"),
    ("call +1 202 555 0143 today", "+1 202 555 0143", "PHONE"),
]


@pytest.mark.parametrize("text,value,label", POSITIVE, ids=[p[0] for p in POSITIVE])
def test_value_after_gate_shaped_cue_is_redacted(text, value, label):
    spans, redacted = labelled(text)
    assert (value, label) in spans
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)


PROSE = [
    "salasana on vaihdettu eilen",
    "the wifi is not working",
    "my password is wrong again",
    "salasana on liian lyhyt",
    "login page ei aukea",
    "login failed again",
    "username and password please",
    "käyttäjätunnus ja salasana",
    "the wifi password is the same as before",
    "username for the portal please",
    "salasana vaihdettiin vuonna 2024",
    "lähetä sähköpostia osoitteeseen maija@example.com",
]


@pytest.mark.parametrize("text", PROSE)
def test_prose_after_cue_stays(text):
    spans, _ = labelled(text)
    assert [lab for _, lab in spans if lab in ("SECRET", "USERNAME")] == [], spans


def test_phone_on_own_line_after_trailing_dash_is_not_glued():
    text = "viitenumero 12-\n040 123 4567"
    spans, _ = labelled(text)
    assert ("040 123 4567", "PHONE") in spans
    assert all(lab != "ACCOUNT_NUMBER" for _, lab in spans)


def test_international_phone_on_own_line_is_split_from_house_number():
    # whole run '1' + 10 digits reads as an account number next to the cue; only the newline split saves it
    text = "tilinumero.\nKatu 1\n+44 2079 4609"
    spans, _ = labelled(text)
    assert ("+44 2079 4609", "PHONE") in spans
    assert all(lab != "ACCOUNT_NUMBER" for _, lab in spans)


def test_international_and_00_forms_of_one_number_share_a_placeholder():
    r = conv("soita +44 20 7946 0958", "tai 0044 20 7946 0958")
    phs = {s["placeholder"] for s in r.spans if s["label"] == "PHONE"}
    assert len([s for s in r.spans if s["label"] == "PHONE"]) == 2
    assert phs == {"[PHONE_1]"}


@pytest.mark.parametrize("text,value", [("salasana123 ei toimi", "salasana123"), ("vanha oli Password2024 kai", "Password2024"),
                                        ("pin1234 on lukossa", "pin1234")])
def test_cue_word_with_glued_digits_is_itself_a_secret(text, value):
    spans, redacted = labelled(text)
    assert (value, "SECRET") in spans
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)


# ---- scope addition: the redactor's HEALTH coverage is a superset of the gate's text.health lexicon ----------
def _gate_health_rows():
    from pets_release.checks.text._lexicon import load_rows

    return load_rows()


@pytest.mark.parametrize("term,lang,match", _gate_health_rows())
def test_every_gate_health_stem_is_redacted(term, lang, match):
    """Each gate lexicon row, as written and inflected, goes through the real lexicon passes; the gate's own
    text.health matcher then finds nothing in the redacted text."""
    from pets_release.checks.text._lexicon import health_terms
    from pets_release.redactor import lexicon

    forms = [term] if match == "exact" else [term, term + "ssa"]
    for form in forms:
        text = f"Asiakas kertoi: {form}. Kiitos."
        ts = [Turn(turn_id="h-t0", text=text, speaker="customer", seq="0")]
        r = redact_conversation("h", ts, passes=lexicon.passes())
        assert health_terms(text), (term, "gate fixture must match")
        assert health_terms(r.texts["h-t0"]) == [], (term, form)


@pytest.mark.parametrize("text", ["soita 040 1234567 diabetes on hallinnassa", "Maija 12.3.2024 sairastui flunssaan",
                                  "pin 4821 astma ei haittaa"])
def test_health_term_stays_redacted_when_its_phrase_loses_an_overlap(text):
    """A higher-priority span inside the HEALTH phrase's left context must not drop the health term itself."""
    from pets_release.checks.text._lexicon import health_terms
    from pets_release.redactor import lexicon

    ts = [Turn(turn_id="h-t0", text=text, speaker="customer", seq="0")]
    r = redact_conversation("h", ts, passes=[StructuredPass(), *lexicon.passes()])
    assert health_terms(text)
    assert health_terms(r.texts["h-t0"]) == []


class _NamePass:
    """Stand-in for a controller-values pass: a cue-priority PERSON span on a known name."""

    name = "test.names"
    labels = frozenset({"PERSON"})

    def __init__(self, word):
        self.word = word

    def run(self, view):
        from pets_release.redactor import PRIORITY_CUE, Candidate

        for i, t in enumerate(view.turns):
            k = t.text.find(self.word)
            if k >= 0:
                yield Candidate(i, k, k + len(self.word), "PERSON", PRIORITY_CUE, None, self.name)


@pytest.mark.parametrize("text", ["äitini Maija sairastaa muistisairautta", "ja Maija sairastaa astmaa nyt"])
def test_health_term_survives_a_higher_priority_name_in_its_phrase(text):
    from pets_release.checks.text._lexicon import health_terms
    from pets_release.redactor import lexicon

    ts = [Turn(turn_id="h-t0", text=text, speaker="customer", seq="0")]
    r = redact_conversation("h", ts, passes=[_NamePass("Maija"), *lexicon.passes()])
    labels = {s["label"] for s in r.spans}
    assert {"PERSON", "HEALTH"} <= labels
    assert health_terms(r.texts["h-t0"]) == [], r.texts["h-t0"]
