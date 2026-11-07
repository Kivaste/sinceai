"""Pipeline seam: passes in, spans + placeholder-substituted turns out."""

from __future__ import annotations

import re

import pytest

from pets_release.redactor import (
    PRIORITY_LEXICON,
    Candidate,
    Turn,
    redact_conversation,
)


class FixedPass:
    """A stand-in lexicon pass that marks every occurrence of given words."""

    def __init__(self, name, words, label, priority=PRIORITY_LEXICON):
        self.name = name
        self.labels = frozenset({label})
        self.words = words
        self.label = label
        self.priority = priority

    def run(self, view):
        for i, t in enumerate(view.turns):
            for w in self.words:
                for m in re.finditer(re.escape(w), t.text):
                    yield Candidate(i, m.start(), m.end(), self.label, self.priority, source=self.name)


def turns(*texts):
    return [Turn(turn_id=f"t{i}", text=x, speaker="customer", seq=str(i)) for i, x in enumerate(texts)]


def test_same_value_same_placeholder_within_conversation():
    p = FixedPass("names", ["Ilona", "Kalle"], "PERSON")
    r = redact_conversation("c1", turns("Ilona here", "Kalle and Ilona"), passes=[p])
    assert r.texts == {"t0": "[PERSON_1] here", "t1": "[PERSON_2] and [PERSON_1]"}
    assert [(s["record_id"], s["start"], s["end"], s["label"], s["placeholder"]) for s in r.spans] == [
        ("t0", 0, 5, "PERSON", "[PERSON_1]"),
        ("t1", 0, 5, "PERSON", "[PERSON_2]"),
        ("t1", 10, 15, "PERSON", "[PERSON_1]"),
    ]


def test_numbering_restarts_per_conversation_so_values_do_not_link():
    p = FixedPass("names", ["Ilona", "Kalle"], "PERSON")
    a = redact_conversation("c1", turns("Ilona"), passes=[p])
    b = redact_conversation("c2", turns("Kalle then Ilona"), passes=[p])
    assert a.texts["t0"] == "[PERSON_1]"
    # Ilona is PERSON_1 in c1 but PERSON_2 in c2: numbers carry no cross-conversation identity.
    assert b.texts["t0"] == "[PERSON_1] then [PERSON_2]"


def test_overlaps_resolved_by_priority_then_length():
    lo = FixedPass("lo", ["Aalto Oy"], "ORG", priority=100)
    hi = FixedPass("hi", ["Aalto"], "PERSON", priority=300)
    r = redact_conversation("c", turns("Aalto Oy"), passes=[lo, hi])
    assert [(s["start"], s["end"], s["label"]) for s in r.spans] == [(0, 5, "PERSON")]


def test_pass_with_bad_offsets_is_rejected():
    class Bad:
        name = "bad"
        labels = frozenset({"PERSON"})

        def run(self, view):
            yield Candidate(0, 3, 99, "PERSON")

    with pytest.raises(ValueError):
        redact_conversation("c", turns("abc"), passes=[Bad()])


def test_pass_emitting_undeclared_label_is_rejected():
    p = FixedPass("names", ["x"], "PERSON")
    p.labels = frozenset({"ORG"})
    with pytest.raises(ValueError):
        redact_conversation("c", turns("x"), passes=[p])


def test_report_lists_passes_run():
    p = FixedPass("names", ["x"], "PERSON")
    r = redact_conversation("c", turns("x"), passes=[p])
    assert r.passes_run == ("names",)


def test_default_placeholder_identity_uses_the_pseudonymisers_normaliser():
    # ticket 06 folds Finnish case endings for names: 'Virtanen' and 'Virtaselle' are one person
    p = FixedPass("names", ["Virtanen", "Virtaselle"], "PERSON")
    r = redact_conversation("c1", turns("Virtanen soitti", "soitin Virtaselle"), passes=[p])
    assert r.texts == {"t0": "[PERSON_1] soitti", "t1": "soitin [PERSON_1]"}
