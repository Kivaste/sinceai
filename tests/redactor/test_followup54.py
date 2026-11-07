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
    # "login failed again": the gate counts 'failed' after a username cue (text and cell rescans), so the redactor
    # takes it too (CS-S1 chain, structured._gate_username_word); pinned in test_username_plain_word.py
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


# ---- round 3 (review of edf51a8): the redactor is at least as broad as the gate's cue rule ---------------
# Rule: after a cue + copula (+ hedges), the first non-prose word is the value, wherever the clause ends;
# a credential-shaped token (the gate's own definition, incl. mixed case) is the value with or without a
# copula; network-key cues (wifi/wlan) take a plain word only when it ends the clause.
ROUND3 = [
    ("username is alfred.", "alfred", "USERNAME"),
    ("username is ahmed.", "ahmed", "USERNAME"),
    ("password is orangeRed.", "orangeRed", "SECRET"),
    ("password is sunflower today", "sunflower", "SECRET"),
    ("password is sunflower for the router", "sunflower", "SECRET"),
    ("username is maijamaa today", "maijamaa", "USERNAME"),
    ("password is probably sunflower now", "sunflower", "SECRET"),
    ("password HunterTwo", "HunterTwo", "SECRET"),
    ("password HunterTwo please", "HunterTwo", "SECRET"),
    ("password is HunterTwo today", "HunterTwo", "SECRET"),
    ("one time code 482913", "482913", "SECRET"),
    ("personal identification number 4821", "4821", "SECRET"),
    ("card verification value 123", "123", "SECRET"),
    ("wifi is sunflower.", "sunflower", "SECRET"),
    ("wlan on kotiverkko.", "kotiverkko", "SECRET"),
    ("pwd is sunflower.", "sunflower", "SECRET"),
]


@pytest.mark.parametrize("text,value,label", ROUND3, ids=[r[0] for r in ROUND3])
def test_round3_value_is_redacted_and_gate_is_clean(text, value, label):
    spans, redacted = labelled(text)
    assert (value, label) in spans
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)


ROUND3_PROSE = [
    "the password was changed.",
    "the password was last changed in 2023",
    "my password is not working today",
    "the wifi is slow in the evening",
    "username and password please",
]


@pytest.mark.parametrize("text", ROUND3_PROSE)
def test_round3_prose_stays(text):
    spans, _ = labelled(text)
    assert [lab for _, lab in spans if lab in ("SECRET", "USERNAME")] == [], spans


def test_00_phone_on_own_line_is_split_from_house_number():
    # whole run '1' + 10 digits reads as an account number next to the cue; only the newline split saves it
    text = "tilinumero.\nKatu 1\n0044 2079 46"
    spans, _ = labelled(text)
    assert ("0044 2079 46", "PHONE") in spans
    assert all(lab != "ACCOUNT_NUMBER" for _, lab in spans)


def test_double_barrelled_name_after_a_short_cue_stem_is_not_a_secret():
    spans, _ = labelled("Pinja Anna-Liisa soitti")
    assert [lab for _, lab in spans if lab == "SECRET"] == [], spans


# ---- round 4 (review of df43b07): the two-part-name exception applies only to ambiguous short-stem cue
# matches ('Pinja' read as 'pin'); after an explicit cue the gate's unmodified credential shape is used, in
# the lookahead too. Failure row: explicit cue + copula + plain word + ordinary word + Title-Title token
# -> only the plain word was redacted, the Title-Title token stayed and both gate scans stopped early.
ROUND4 = [
    ("password is kissa talo Anna-Liisa", "Anna-Liisa"),
    ("password is kissa talo Anna-Liisa!", "Anna-Liisa"),
    ("salasana on kissa talo Anna-Liisa", "Anna-Liisa"),
    ("password Anna-Liisa", "Anna-Liisa"),
    ("salasana taitaa olla Anna-Liisa", "Anna-Liisa"),
]


@pytest.mark.parametrize("text,value", ROUND4, ids=[r[0] for r in ROUND4])
def test_round4_title_title_credential_after_explicit_cue_is_redacted(text, value):
    spans, redacted = labelled(text)
    # a trailing '!' may be part of the password and is redacted with it
    assert any(lab == "SECRET" and v.rstrip("!") == value for v, lab in spans), spans
    assert value not in redacted
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)


_SIX = ("rescan.secrets", "rescan.usernames", "rescan.phones", "text.secrets", "text.usernames", "text.phones")


def _run_six(run_checks, rows, folder):
    """Statuses of the six secret/username/phone checks via the production runner on one text column."""
    import csv

    from pets_release.checks import all_checks

    folder.mkdir(parents=True)
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["turn_id", "conversation_id", "seq", "speaker", "text"])
        w.writerows([[f"T{n + 1}", f"C{n + 1}", "1", "customer", t] for n, t in enumerate(rows)])
    contract = {
        "files": {"turns.csv": {"required": ["turn_id", "conversation_id", "seq", "text"], "columns": {
            "turn_id": {"form": "^T[0-9]+$", "params": {}},
            "conversation_id": {"form": "^C[0-9]+$", "params": {}},
            "seq": {"form": "integer", "params": {}},
            "speaker": {"form": "enum", "params": {"values": ["customer", "agent"]}},
            "text": {"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}},
        }}},
        "qi": [], "tokens": [], "healthInTextRequired": True,
    }
    checks = [c for c in all_checks() if c.name in _SIX]
    assert len(checks) == len(_SIX)
    res = run_checks(folder, contract, {"phase": "gate"}, checks=checks)
    by = {r.check: r for r in res.records}
    assert sorted(by) == sorted(_SIX)
    return {n: by[n].status for n in _SIX}


def test_round4_title_title_credential_release_checks_are_clean(tmp_path):
    """The production run_checks on a redacted text column finds no secret; on the raw rows it does."""
    from pets_release.checks import run_checks

    raw = _run_six(run_checks, [t for t, _ in ROUND4], tmp_path / "raw")
    assert raw["text.secrets"] == "fail" and raw["rescan.secrets"] == "fail", raw
    rows = [labelled(t)[1] for t, _ in ROUND4]
    assert all(v not in r for (_, v), r in zip(ROUND4, rows))
    red = _run_six(run_checks, rows, tmp_path / "red")
    assert all(s == "pass" for s in red.values()), red


# Round 4 (Grok, review of df43b07). Rules: a short cue stem that is a proper alphabetic prefix of a longer
# word is no cue ('Pinja'), and after a cue the gate's credential shape is used unmodified (no name rule);
# the gate's hedges and copulas are skipped before the value like fillers; 'secret key' is a strong cue
# (bare 'secret' is not); the lookahead passes over commas like the gate.
# Failure rows (trigger -> result at df43b07):
#   whole-word cue + Title-Title token, no copula   -> token kept (name rule)
#   cue + copula + non-filler hedge + plain word    -> hedge scored as the value, word kept
#   cue + it's/its + plain word                     -> copula not recognised, word kept
#   'secret key' + copula + plain word              -> not a strong cue, word kept
#   cue + copula + word + ',' + credential token    -> lookahead stopped at the comma
ROUND4_GROK = [
    ("token Anna-Liisa", "Anna-Liisa"),
    ("api-key Anna-Liisa please", "Anna-Liisa"),
    ("password is maybe sunflower", "sunflower"),
    ("password is perhaps sunflower today", "sunflower"),
    ("salasana on ehkä kissakala", "kissakala"),
    ("salasana on luultavasti kissakala", "kissakala"),
    ("lösenordet är kanske solrosen", "solrosen"),
    ("lösenordet är nog solrosen", "solrosen"),
    ("lösenordet är typ solrosen", "solrosen"),
    ("lösenordet är fortfarande solrosen", "solrosen"),
    ("the password, it's sunflower", "sunflower"),
    ("password its sunflower", "sunflower"),
    ("secret key is sunflower", "sunflower"),
    ("the secret key is sunflower today", "sunflower"),
    ("password is kissa, Koira2024", "Koira2024"),
]


@pytest.mark.parametrize("text,value", ROUND4_GROK, ids=[r[0] for r in ROUND4_GROK])
def test_round4_grok_value_is_redacted_and_gate_is_clean(text, value):
    raw = gate_hits(text)
    assert raw["rescan.secrets"] or raw["text.secrets"], ("fixture must be a gate hit", raw)
    spans, redacted = labelled(text)
    assert any(lab == "SECRET" and v.rstrip("!") == value for v, lab in spans), spans
    assert value not in redacted
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)


def test_redactor_copulas_and_hedges_cover_the_gates():
    from pets_release.checks import _cues
    from pets_release.redactor import structured

    assert _cues.COPULAS <= structured.COPULAS
    assert _cues.HEDGES <= structured.HEDGES


def test_round4_grok_release_checks_are_clean(tmp_path):
    from pets_release.checks import run_checks

    rows = [labelled(t)[1] for t, _ in ROUND4_GROK]
    red = _run_six(run_checks, rows, tmp_path / "red")
    assert all(s == "pass" for s in red.values()), red


@pytest.mark.parametrize("text", ["the secret is sunflower today", "Pinja Anna-Liisa soitti", "Pinja on kotona"])
def test_round4_bare_secret_and_stem_prefix_are_no_strong_cue(text):
    spans, _ = labelled(text)
    assert [lab for _, lab in spans if lab == "SECRET"] == [], spans


def test_plain_word_after_copula_and_a_later_credential_are_both_redacted():
    text = "salasana on kissa ja Koira2024"
    spans, redacted = labelled(text)
    assert ("kissa", "SECRET") in spans and ("Koira2024", "SECRET") in spans
    assert not any(gate_hits(redacted).values()), gate_hits(redacted)
