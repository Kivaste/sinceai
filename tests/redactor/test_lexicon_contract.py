"""The lexicon-pass loading contract (ticket 13 plugs in here) and determinism of the pipeline."""

from __future__ import annotations

import sys
import types

import pytest

from pets_release.redactor import (
    PRIORITY_LEXICON,
    Candidate,
    StructuredPass,
    Turn,
    pipeline,
    redact_conversation,
)


def test_missing_lexicon_is_an_error_when_required(monkeypatch):
    monkeypatch.setattr(pipeline, "LEXICON_MODULE", "pets_release.redactor._absent_lexicon_for_test")
    with pytest.raises(ModuleNotFoundError):
        pipeline.default_passes(require_lexicon=True)
    assert [p.name for p in pipeline.default_passes()] == ["structured"]


def test_lexicon_module_passes_are_loaded(monkeypatch):
    class Names:
        name = "lexicon-person"
        labels = frozenset({"PERSON"})

        def run(self, view):
            for i, t in enumerate(view.turns):
                k = t.text.find("Ilona")
                if k >= 0:
                    yield Candidate(i, k, k + 5, "PERSON", PRIORITY_LEXICON)

    mod = types.ModuleType("pets_release.redactor._fake_lexicon")
    mod.passes = lambda: [Names()]
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(pipeline, "LEXICON_MODULE", mod.__name__)
    passes = pipeline.default_passes(require_lexicon=True)
    assert [p.name for p in passes] == ["structured", "lexicon-person"]
    r = redact_conversation("c", [Turn("t0", "Ilona, numero on 040 123 4567")], passes=passes)
    assert r.texts["t0"] == "[PERSON_1], numero on [PHONE_1]"


def test_broken_lexicon_import_is_not_swallowed(monkeypatch):
    # a lexicon package that exists but fails on its own import must surface, not degrade silently
    def boom(name, *a, **k):
        raise ModuleNotFoundError("No module named 'some_dependency'", name="some_dependency")

    monkeypatch.setattr(pipeline.importlib, "import_module", boom)
    with pytest.raises(ModuleNotFoundError):
        pipeline.default_passes()


def test_same_input_same_output_and_pass_order_does_not_matter():
    turns = [Turn("t0", "hetu 131052-308T ja numero 040 123 4567", "customer", "1"),
             Turn("t1", "maija piste m at posti piste example", "customer", "2")]

    class Echo:
        name = "zz-echo"
        labels = frozenset({"PERSON"})

        def run(self, view):
            yield Candidate(0, 0, 4, "PERSON", PRIORITY_LEXICON)

    a = redact_conversation("c", turns, passes=[StructuredPass(), Echo()])
    b = redact_conversation("c", turns, passes=[Echo(), StructuredPass()])
    assert a.spans == b.spans and a.texts == b.texts
    assert a.spans == redact_conversation("c", turns, passes=[StructuredPass(), Echo()]).spans
