"""Behaviour added while measuring on the train split: per-conversation party names, cue runs, age/date edge cases.

All strings are hand-made synthetic text (no kit rows).
"""

from __future__ import annotations

import pytest

from pets_release.redactor.lexicon import Gazetteer, loader, passes
from pets_release.redactor.passes import ConversationView, Turn


def spans(text: str, label: str, gz: Gazetteer | None = None, conversation_id: str = "c1") -> list[str]:
    view = ConversationView(conversation_id, (Turn("t1", text),))
    out = []
    for p in passes(gz):
        for c in p.run(view):
            if c.label == label:
                out.append(text[c.start:c.end])
    return sorted(out, key=text.index)


class TestPartyNames:
    GZ = Gazetteer.from_tables(
        full_names=["Zorbas Quenzel", "Maija Quenzel"],
        parties={"c1": ["Zorbas Quenzel"]},
    )

    def test_lowercase_name_of_this_conversations_party_counts(self):
        assert spans("joo tässä zorbas puhelimessa", "PERSON", self.GZ, "c1") == ["zorbas"]

    def test_lowercase_gazetteer_name_of_another_conversation_does_not(self):
        assert spans("joo tässä zorbas puhelimessa", "PERSON", self.GZ, "c2") == []

    def test_capitalised_gazetteer_name_counts_in_any_conversation(self):
        assert spans("Soitin Maija Quenzelille", "PERSON", self.GZ, "c2") == ["Maija Quenzelille"]

    def test_lowercase_without_party_table_needs_a_cue_or_pair(self):
        gz = Gazetteer.from_tables(full_names=["Zorbas Quenzel"])
        assert spans("joo tässä zorbas puhelimessa", "PERSON", gz) == ["zorbas"]  # no parties given: any lower-case gazetteer name of 4+ letters

    def test_function_word_that_looks_like_a_name_stem_is_not_a_name(self):
        gz = Gazetteer.from_tables(full_names=["Ole Hansen"])
        assert spans("hei olen aika väsynyt", "PERSON", gz) == []


class TestCueRuns:
    def test_org_lowercase_run_after_operator_cue(self):
        assert spans("operaattori on foo bar ja haluan vaihtaa", "ORG") == ["foo bar"]

    def test_org_after_from_needs_two_words(self):
        assert spans("I am calling from Meridian Logistics today", "ORG") == ["Meridian Logistics"]
        assert spans("I am calling from Raisio today", "ORG") == []

    def test_unknown_place_with_ending_after_location_cue(self):
        assert spans("Hei, olen Zzyzxvillessä nyt", "LOCATION") == ["Zzyzxvillessä"]
        assert spans("Hei, olen Zzyzxvillessä nyt", "PERSON") == []

    def test_minor_place_that_is_also_a_name_is_a_name(self):
        gz = Gazetteer.from_tables(full_names=["Salla Virtanen"])
        assert spans("Terveisin Salla", "LOCATION", gz) == []
        assert spans("Terveisin Salla", "PERSON", gz) == ["Salla"]


class TestAgeAndDate:
    def test_age_from_on_n_vuotta(self):
        assert spans("tyttäreni on 12 vuotta", "AGE") == ["12"]

    def test_duration_is_not_age(self):
        assert spans("sopimus on 2 vuotta voimassa", "AGE") == []

    def test_month_day_keeps_the_dot_out(self):
        assert spans("maaliskuun 15. päivä", "DATE") == ["maaliskuun 15"]

    def test_numeric_date_keeps_trailing_dot(self):
        assert spans("tulen 15.3. kotiin", "DATE") == ["15.3."]


class TestEditableRules:
    def test_rules_are_read_from_the_csv(self, tmp_path):
        import shutil

        for f in loader.DATA_DIR.glob("*.csv"):
            shutil.copy(f, tmp_path / f.name)
        rows = (tmp_path / "boundaries.csv").read_text(encoding="utf-8").splitlines()
        rows = [r.replace("@person_merge,fi,PERSON,rule,merge", "@person_merge,fi,PERSON,rule,split") for r in rows]
        (tmp_path / "boundaries.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        view = ConversationView("c1", (Turn("t1", "Nimeni on Aino Virtanen"),))
        out = [c for p in passes(None, tmp_path) for c in p.run(view) if c.label == "PERSON"]
        assert len(out) == 2

    def test_excel_bom_is_tolerated(self, tmp_path):
        f = tmp_path / "x.csv"
        f.write_bytes(b"\xef\xbb\xbfterm,lang,label,match,boundary,notes\nfoo,fi,PERSON,lemma,case_ending,n\n")
        assert [e.term for e in loader.read_csv(f)] == ["foo"]

    def test_unknown_match_kind_is_refused(self, tmp_path):
        f = tmp_path / "x.csv"
        f.write_text("term,lang,label,match,boundary,notes\nfoo,fi,PERSON,bogus,x,n\n", encoding="utf-8")
        with pytest.raises(ValueError):
            loader.read_csv(f)
