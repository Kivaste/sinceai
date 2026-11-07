"""Lexicon package contract: CSV schema, runtime-only gazetteer, pipeline integration, determinism."""

from __future__ import annotations

import csv
import pathlib
import re

import pytest

from pets_release.redactor import lexicon
from pets_release.redactor.labels import LEXICON_LABELS
from pets_release.redactor.lexicon import Gazetteer, loader, passes
from pets_release.redactor.passes import ConversationView, Turn
from pets_release.redactor.pipeline import default_passes, redact_conversation

DATA = pathlib.Path(lexicon.__file__).parent / "data"
COLUMNS = ["term", "lang", "label", "match", "boundary", "notes"]


def test_int_rule_with_non_integer_value_is_refused():
    rules = loader.Rules({("@health_left", "HEALTH"): "four"})
    with pytest.raises(ValueError, match="@health_left"):
        rules.int_of("@health_left", "HEALTH", 3)
    assert loader.Rules({}).int_of("@health_left", "HEALTH", 3) == 3  # an absent row keeps the default


def test_no_placeholder_question_marks_in_lexicon_terms():
    """A literal '?' in a term is encoding damage (the entry would never match)."""
    bad = [(f.name, n) for f in sorted(DATA.glob("*.csv")) for n, e in enumerate(loader.read_csv(f), 2) if "?" in e.term]
    assert bad == []


def test_stopword_set_has_no_placeholder_question_marks():
    from pets_release.redactor.lexicon import places

    for name in dir(places):
        v = getattr(places, name)
        if name.isupper() and isinstance(v, (set, frozenset, list, tuple)):
            assert not [w for w in v if isinstance(w, str) and "?" in w], name


def test_restored_finnish_cues_and_denylist_words_take_effect():
    from pets_release.redactor.lexicon import Gazetteer  # noqa: F401

    terms = {e.term for f in DATA.glob("*.csv") for e in loader.read_csv(f)}
    assert {"nimellä", "yhteyshenkilö", "hänen nimensä on", "lääkäri", "työnantaja on", "että", "hän", "mikäli"} <= terms


def test_csv_columns_are_pinned():
    files = sorted(DATA.glob("*.csv"))
    assert files, "no lexicon CSVs"
    for f in files:
        with open(f, encoding="utf-8", newline="") as fh:
            assert next(csv.reader(fh)) == COLUMNS, f.name


def test_csv_rows_valid():
    for f in sorted(DATA.glob("*.csv")):
        with open(f, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                assert row["term"].strip() and row["label"] in LEXICON_LABELS, (f.name, row["label"])
                assert row["match"] in loader.MATCH_KINDS, (f.name, row["match"])
                assert None not in row.values()


def test_loader_refuses_bad_header(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("term,label\nx,PERSON\n", encoding="utf-8")
    try:
        loader.read_csv(bad)
    except ValueError:
        return
    raise AssertionError("bad header accepted")


def test_passes_cover_exactly_the_seven_labels():
    got = set()
    for p in passes():
        got |= set(p.labels)
    assert got == {"PERSON", "ADDRESS", "LOCATION", "ORG", "DATE", "AGE", "HEALTH"}
    names = [p.name for p in passes()]
    assert len(names) == len(set(names))


def test_pipeline_picks_up_lexicon_and_keeps_rest_of_turn():
    turns = [Turn("t1", "Hei, nimeni on Aino Virtanen ja minulla on diabetes mutta haluan vaihtaa laskun.")]
    assert any(p.name.startswith("lexicon.") for p in default_passes(require_lexicon=True))
    red = redact_conversation("c1", turns)
    out = red.texts["t1"]
    assert "[PERSON_1]" in out and "[HEALTH_1]" in out
    assert "haluan vaihtaa laskun" in out and "diabetes" not in out and "Virtanen" not in out
    labels = {s["label"] for s in red.spans}
    assert labels == {"PERSON", "HEALTH"}


def test_gazetteer_is_runtime_only(tmp_path, monkeypatch):
    before = sorted(p.name for p in DATA.iterdir())
    monkeypatch.chdir(tmp_path)
    gz = Gazetteer.from_tables(full_names=["Zorbas Quenzel"], cities=["Zzyzxville"], streets=["Qwertykatu 4"])
    view = ConversationView("c", (Turn("t", "Zorbas Quenzel asuu Zzyzxvillessä"),))
    for p in passes(gz):
        list(p.run(view))
    assert sorted(p.name for p in DATA.iterdir()) == before
    assert list(tmp_path.iterdir()) == []
    for f in DATA.glob("*.csv"):
        text = f.read_text(encoding="utf-8").lower()
        assert "quenzel" not in text and "zzyzx" not in text and "qwerty" not in text


def test_package_never_writes_files():
    src = pathlib.Path(lexicon.__file__).parent
    for f in src.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for needle in ("write_text", "write_bytes", "pickle", "json.dump", "csv.writer"):
            assert needle not in text, (f.name, needle)
        assert not re.search(r"open\([^)]*[\"'][wax]b?\+?[\"']", text), f.name


def test_committed_lexicons_hold_no_digits_in_name_files():
    for name in ("names_given.csv", "names_family.csv", "places.csv"):
        with open(DATA / name, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                assert not any(ch.isdigit() for ch in row["term"]), (name, row["term"])


def test_deterministic():
    view = ConversationView(
        "c",
        (Turn("t1", "Nimeni on Aino Virtanen, Koivukatu 12 B 14, 20100 Turku, olen 83-vuotias, syntynyt 15.3.1942"),),
    )

    def run():
        return [(c.turn_index, c.start, c.end, c.label, c.priority, c.key, c.source) for p in passes() for c in p.run(view)]

    assert run() == run()
    assert len(run()) >= 5
