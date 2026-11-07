"""Boundary-only unit tests per label: which characters the span covers, nothing about the rest.

Cue words are excluded, spoken separators included, case endings follow the per-label rule in
``data/boundaries.csv``. All strings here are hand-made synthetic text.
"""

from __future__ import annotations

import pytest

from pets_release.redactor.lexicon import Gazetteer, passes
from pets_release.redactor.passes import ConversationView, Turn
from pets_release.redactor.pipeline import redact_conversation


def spans(text: str, label: str, gazetteer: Gazetteer | None = None) -> list[str]:
    view = ConversationView("c1", (Turn("t1", text),))
    out = []
    for p in passes(gazetteer):
        for c in p.run(view):
            if c.label == label:
                assert c.turn_index == 0 and 0 <= c.start < c.end <= len(text)
                out.append(text[c.start:c.end])
    return sorted(out, key=text.index)


def all_labels(text: str, gazetteer: Gazetteer | None = None) -> list[tuple[str, str]]:
    """Labels after the pipeline's overlap resolution (labels never overlap)."""
    red = redact_conversation("c1", [Turn("t1", text)], passes=passes(gazetteer))
    return [(s["label"], text[s["start"]:s["end"]]) for s in red.spans]


# ---------------------------------------------------------------- PERSON
class TestPerson:
    def test_strong_cue_excluded_full_name_one_span(self):
        assert spans("Nimeni on Aino Virtanen.", "PERSON") == ["Aino Virtanen"]

    def test_relation_cue_excluded(self):
        assert spans("äitini Pirkko soitti eilen", "PERSON") == ["Pirkko"]

    def test_first_name_alone(self):
        assert spans("Kiitos Tiina, hyvää päivänjatkoa", "PERSON") == ["Tiina"]

    def test_case_ending_included(self):
        assert spans("Terveisin Pirkko Mäkisen puolesta", "PERSON") == ["Pirkko Mäkisen"]
        assert spans("Soitin Ainolle", "PERSON") == ["Ainolle"]

    def test_case_ending_rule_is_per_label_and_editable(self, tmp_path, monkeypatch):
        from pets_release.redactor.lexicon import loader

        rules = loader.load_rules()
        assert rules.case_ending("PERSON") == "include"
        assert rules.case_ending("LOCATION") == "include"

    def test_unknown_name_after_strong_cue(self):
        assert spans("My name is Zelda Quux and I need help", "PERSON") == ["Zelda Quux"]

    def test_unknown_capitalised_word_without_cue_is_not_a_name(self):
        assert spans("Haluan puhua Zelda tuotteesta", "PERSON") == []

    def test_lowercase_asr_name_after_cue(self):
        assert spans("hei olen aino virtanen ja", "PERSON") == ["aino virtanen"]

    def test_common_words_that_are_names_are_not_person(self):
        assert spans("Toivon että onneksi sataa lunta", "PERSON") == []
        assert spans("toivon kaikkea hyvää", "PERSON") == []

    def test_bot_and_company_names_are_not_person(self):
        assert spans("Hei Aava, olen Aallokko asiakas", "PERSON") == []

    def test_two_people_split(self):
        assert spans("Aino ja Matti soittivat", "PERSON") == ["Aino", "Matti"]

    def test_gazetteer_name_with_case_ending(self):
        gz = Gazetteer.from_tables(full_names=["Zorbas Quenzel"])
        assert spans("Asiakas on Quenzelin vaimo", "PERSON", gz) == ["Quenzelin"]
        assert spans("Zorbas Quenzel soitti", "PERSON", gz) == ["Zorbas Quenzel"]

    def test_gazetteer_lowercase_full_name(self):
        gz = Gazetteer.from_tables(full_names=["Zorbas Quenzel"])
        assert spans("tässä zorbas quenzel", "PERSON", gz) == ["zorbas quenzel"]

    def test_gazetteer_lone_lowercase_token_is_not_enough(self):
        gz = Gazetteer.from_tables(full_names=["Toivo Kallio"])
        assert spans("toivon että kallio on kaunis", "PERSON", gz) == []


# ---------------------------------------------------------------- ADDRESS
class TestAddress:
    def test_postcode_and_town_absorbed(self):
        assert spans("Asun osoitteessa Koivukatu 12 B 14, 20100 Turku.", "ADDRESS") == ["Koivukatu 12 B 14, 20100 Turku"]

    def test_without_postcode(self):
        assert spans("osoitteeni on Kuusitie 3 A", "ADDRESS") == ["Kuusitie 3 A"]

    def test_street_and_number_only(self):
        assert spans("Mannerheimintie 5 on tuttu", "ADDRESS") == ["Mannerheimintie 5"]

    def test_inflected_street_word(self):
        assert spans("Asun Koivukadulla 12 nykyään", "ADDRESS") == ["Koivukadulla 12"]

    def test_apartment_marker(self):
        assert spans("Aleksanterinkatu 4 as. 7, 00100 Helsinki", "ADDRESS") == ["Aleksanterinkatu 4 as. 7, 00100 Helsinki"]

    def test_town_inside_address_is_not_a_second_location(self):
        labels = [l for l, _ in all_labels("Koivukatu 12, 20100 Turku")]
        assert labels == ["ADDRESS"]

    def test_street_word_without_number_is_not_an_address(self):
        assert spans("Koivukatu on pitkä", "ADDRESS") == []

    def test_price_after_unrelated_word_is_not_an_address(self):
        assert spans("Tämä maksaa 12 euroa", "ADDRESS") == []

    def test_standalone_postcode_and_known_town(self):
        assert spans("postinumero 00100 Helsinki", "ADDRESS") == ["00100 Helsinki"]

    def test_english_address(self):
        assert spans("I live at 12 Birch Street", "ADDRESS") == ["12 Birch Street"]


# ---------------------------------------------------------------- LOCATION
class TestLocation:
    def test_country_with_case_ending(self):
        assert spans("Matkustan Thaimaassa ensi kuussa", "LOCATION") == ["Thaimaassa"]

    def test_town_with_case_ending(self):
        assert spans("Asun nyt Raisiossa", "LOCATION") == ["Raisiossa"]
        assert spans("Muutin Turusta Helsinkiin", "LOCATION") == ["Turusta", "Helsinkiin"]

    def test_bare_town(self):
        assert spans("Raisio", "LOCATION") == ["Raisio"]

    def test_gazetteer_city(self):
        gz = Gazetteer.from_tables(cities=["Zzyzxville"])
        assert spans("Asun Zzyzxvillessä", "LOCATION", gz) == ["Zzyzxvillessä"]

    def test_university_is_org_not_location(self):
        labels = [l for l, _ in all_labels("Opiskelen Turun yliopisto")]
        assert labels == ["ORG"]


# ---------------------------------------------------------------- ORG
class TestOrg:
    def test_legal_suffix_name_is_one_span(self):
        assert spans("Työnantajani on Meridian Logistics Oy tällä hetkellä", "ORG") == ["Meridian Logistics Oy"]

    def test_controller_name_is_not_org(self):
        assert spans("Aallokko Telecom Oy lähetti laskun", "ORG") == []

    def test_known_bank(self):
        assert spans("Pankkini on Nordea", "ORG") == ["Nordea"]

    def test_employer_with_case_ending_wins_over_town(self):
        assert all_labels("Olen töissä Nokialla") == [("ORG", "Nokialla")]

    def test_suffix_without_name_is_not_org(self):
        assert spans("Oy on lyhenne", "ORG") == []


# ---------------------------------------------------------------- DATE
class TestDate:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Syntymäpäiväni on 15.3.1985 kyllä", ["15.3.1985"]),
            ("Muutan 15.3. uuteen kotiin", ["15.3."]),
            ("born 1985-03-15 in", ["1985-03-15"]),
            ("on 15/3/2025 tehty", ["15/3/2025"]),
            ("Moved on March 15, 2025 sadly", ["March 15, 2025"]),
            ("the 15 March 2025 visit", ["15 March 2025"]),
            ("maaliskuun 15. päivä", ["maaliskuun 15"]),
            ("15. maaliskuuta 2025 mennessä", ["15. maaliskuuta 2025"]),
        ],
    )
    def test_dates(self, text, expected):
        assert spans(text, "DATE") == expected

    @pytest.mark.parametrize(
        "text",
        ["Reititin on 192.168.1.1 osoitteessa", "Hinta on 3.5 euroa", "versio 2.4.1 asennettu", "maaliskuussa tulee lasku", "Kello 12.30 tiistaina"],
    )
    def test_not_dates(self, text):
        assert spans(text, "DATE") == []


# ---------------------------------------------------------------- AGE
class TestAge:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("olen 83-vuotias ja", ["83"]),
            ("I am 45 years old", ["45"]),
            ("she is a 7-year-old", ["7"]),
            ("olen 62 vuotta vanha", ["62"]),
            ("jag är 70 år gammal", ["70"]),
            ("ikäni on 59", ["59"]),
        ],
    )
    def test_age_is_the_number_only(self, text, expected):
        assert spans(text, "AGE") == expected

    @pytest.mark.parametrize(
        "text",
        ["olen 5 minuuttia myöhässä", "tilasin sen 2 vuotta sitten", "sopimus kestää 24 kuukautta", "I'm 5 minutes away", "Hinta 83 euroa"],
    )
    def test_not_age(self, text):
        assert spans(text, "AGE") == []


# ---------------------------------------------------------------- HEALTH
class TestHealth:
    def test_phrase_level_not_just_the_term(self):
        assert spans("minulla on kuulolaite", "HEALTH") == ["minulla on kuulolaite"]

    def test_rest_of_the_turn_is_kept(self):
        text = "Hei, minulla on diabetes ja haluan vaihtaa laskun."
        assert spans(text, "HEALTH") == ["minulla on diabetes"]

    def test_english(self):
        assert spans("Well, I have asthma. Can you help?", "HEALTH") == ["I have asthma"]

    def test_connective_not_in_span(self):
        assert spans("En voi tulla koska sairastan masennusta", "HEALTH") == ["sairastan masennusta"]

    def test_no_health_no_span(self):
        assert spans("Haluan vaihtaa laskun ja nettiliittymän", "HEALTH") == []

    def test_does_not_cross_sentence(self):
        got = spans("Se on tärkeää. Diabetes", "HEALTH")
        assert got == ["Diabetes"]
