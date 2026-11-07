"""Normalisation before hashing, first-name linking, and non-reversibility.

All values are hand-made synthetic examples, never kit data.
"""

import hashlib
import random

import pytest

from pets_release.pseudonym import MasterKey, Scope, normalise, pseudonymiser_for

TEST_KEY = "synthetic-test-key-0123456789abcdef-not-real"
REL = Scope.release("0123456789abcdef")


def tok(value, label, scope=REL, p=None):
    p = p or pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    return p.token(value, label=label, scope=scope)


@pytest.mark.parametrize(
    "label,variants",
    [
        (
            "NATIONAL_ID",
            [
                "010190-123a",
                " 010190 - 123A ",
                "nolla yksi nolla yksi yhdeksän nolla viiva yksi kaksi kolme A",
            ],
        ),
        (
            "NATIONAL_ID",
            [
                "010190-123A",
                "noll ett noll ett nio noll streck ett två tre a",
                "zero one zero one nine zero dash one two three A",
            ],
        ),
        (
            "PHONE",
            [
                "+358 40 123 4567",
                "040-1234567",
                "040 123 45 67",
                "nolla neljä nolla yksi kaksi kolme neljä viisi kuusi seitsemän",
                "00358401234567",
                "+358 (0)40 123 4567",
                "+358 040 123 4567",
            ],
        ),
        (
            "PHONE",
            ["+46 70 123 45 67", "0046701234567", "+46 (0)70 123 45 67"],
        ),
        (
            "PAYMENT_CARD",
            ["4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"],
        ),
        ("IBAN", ["FI21 1234 5600 0007 85", "fi2112345600000785"]),
        ("EMAIL", [" Anna.Example@Example.FI ", "anna.example@example.fi"]),
        ("PERSON", ["Anna", " anna ", "ANNA"]),
        ("PERSON", ["Matti Virtanen", "Matti Virtasen", "matti  virtaselle"]),
        ("RECORD_KEY", ["V-0001", " V-0001 "]),
    ],
)
def test_variants_of_one_value_get_one_token(label, variants):
    assert len({tok(v, label) for v in variants}) == 1


@pytest.mark.parametrize(
    "label,a,b",
    [
        ("NATIONAL_ID", "010190-123A", "010190+123A"),  # century sign matters
        ("PHONE", "0401234567", "0401234568"),
        ("RECORD_KEY", "V-0001", "v-0001"),  # record keys are exact
        ("RECORD_KEY", "V-0001", "V0001"),
        ("PERSON", "Johan", "Johanna"),
        ("PERSON", "Anna", "Hanna"),
        # distinct names that differ by what looks like a case ending
        ("PERSON", "Anna", "Annan"),
        ("PERSON", "Kristia", "Kristian"),
        ("PERSON", "Hans", "Hansen"),
        ("PERSON", "Jens", "Jensen"),
        ("PERSON", "Lars", "Lar"),
        ("PERSON", "Isabella", "Isabelle"),
        ("PERSON", "Jane", "Janelle"),
        ("PERSON", "Lari", "Larissa"),
        ("PERSON", "Noe", "Noelle"),
        ("PERSON", "Erik", "Eriks"),
    ],
)
def test_distinct_values_stay_distinct(label, a, b):
    assert tok(a, label) != tok(b, label)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Anna", "Annan"),
        ("Hans", "Hansen"),
        ("Erik", "Eriks"),
        ("Isabella", "Isabelle"),
        ("Lari", "Larissa"),
        ("Augu", "Augusta"),
    ],
)
def test_distinct_names_stay_distinct_in_a_fresh_conversation(a, b):
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    assert p.token(a, label="PERSON", scope=c) != p.token(b, label="PERSON", scope=c)
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    assert p.token(b, label="PERSON", scope=c) != p.token(a, label="PERSON", scope=c)


@pytest.mark.parametrize(
    "seen,inflected",
    [
        ("Anna", "Annalle"),
        ("Anna", "Annalta"),
        ("Maria", "Marialla"),
        ("Kalle", "Kallelle"),
    ],
)
def test_case_ending_links_to_a_name_seen_in_the_conversation(seen, inflected):
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    base = p.token(seen, label="PERSON", scope=c)
    assert p.token(inflected, label="PERSON", scope=c) == base


def test_inflected_first_name_links_through_to_the_full_name():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    full = p.token("Anna Korhonen", label="PERSON", scope=c)
    assert p.token("Annalle", label="PERSON", scope=c) == full


def test_inflected_surname_in_full_name_links_only_to_the_same_full_name():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    full = p.token("Maria Salo", label="PERSON", scope=c)
    assert p.token("Maria Salolle", label="PERSON", scope=c) == full
    # same surname form with another first name is not linked to Maria Salo
    assert p.token("Liisa Salolle", label="PERSON", scope=c) != full
    # a surname that looks like a seen bare name plus an ending is another person
    p.token("Anna", label="PERSON", scope=c)
    kofi = p.token("Kofi Annan", label="PERSON", scope=c)
    assert kofi != p.token("Kofi Anna", label="PERSON", scope=c)


def test_name_seen_as_itself_is_not_reinterpreted_as_an_inflection():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    annan = p.token("Annan", label="PERSON", scope=c)
    anna = p.token("Anna", label="PERSON", scope=c)
    assert annan != anna
    assert p.token("Annan", label="PERSON", scope=c) == annan


def test_bare_name_does_not_link_to_a_different_full_name():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    johan = p.token("Johan Lind", label="PERSON", scope=c)
    assert p.token("Johanna", label="PERSON", scope=c) != johan
    stefan = p.token("Stefan Berg", label="PERSON", scope=c)
    assert p.token("Stefa", label="PERSON", scope=c) != stefan


@pytest.mark.parametrize("label", ["RECORD_KEY", "NATIONAL_ID"])
@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_empty_identifier_values_are_refused(label, value):
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    with pytest.raises(ValueError) as e:
        p.token(value, label=label, scope=REL)
    assert repr(value) not in str(e.value)


def test_normalise_is_public_and_label_aware():
    assert normalise("040-123 4567", "PHONE") == "+358401234567"
    assert normalise("+46 70 123 45 67", "PHONE") == "+46701234567"
    assert normalise("Virtaselle", "PERSON") == normalise("Virtanen", "PERSON")
    assert normalise("+358 (0)40 123 4567", "PHONE") == "+358401234567"


@pytest.mark.parametrize(
    "a,b",
    [
        ("+358 70 123 4567", "+46 70 123 4567"),
        ("00358701234567", "0046701234567"),
        ("+46 70 123 4567", "070 123 4567"),  # domestic defaults to FI
        ("+1 701 234 5670", "0701 234 5670"),
    ],
)
def test_same_national_digits_in_different_countries_stay_distinct(a, b):
    assert normalise(a, "PHONE") != normalise(b, "PHONE")
    assert tok(a, "PHONE") != tok(b, "PHONE")


def test_domestic_phone_country_is_a_parameter():
    se = [
        "+46 70 123 45 67",
        "070-1234567",
        "noll sju noll ett två tre fyra fem sex sju",
    ]
    assert {normalise(v, "PHONE", phone_country="46") for v in se} == {"+46701234567"}
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY), phone_country="46")
    assert len({p.token(v, label="PHONE", scope=REL) for v in se}) == 1
    assert p.token("070-1234567", label="PHONE", scope=REL) != tok(
        "070-1234567", "PHONE"
    )
    with pytest.raises(ValueError):
        normalise("0401234567", "PHONE", phone_country="+358")
    with pytest.raises(ValueError):
        normalise("x", "NOT_A_LABEL")


def test_bare_first_name_links_to_full_name_seen_earlier_in_conversation():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c1 = Scope.conversation("conv-1")
    full = p.token("Matti Virtanen", label="PERSON", scope=c1)
    assert p.token("Matti", label="PERSON", scope=c1) == full
    assert p.token("matti", label="PERSON", scope=c1) == full
    # a different conversation has its own (empty) link table
    c2 = Scope.conversation("conv-2")
    bare_c2 = p.token("Matti", label="PERSON", scope=c2)
    assert bare_c2 != p.token("Matti Virtanen", label="PERSON", scope=c2)


def test_first_name_seen_before_full_name_is_not_linked_retroactively():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    bare = p.token("Anna", label="PERSON", scope=c)
    full = p.token("Anna Korhonen", label="PERSON", scope=c)
    assert bare != full
    assert p.token("Anna", label="PERSON", scope=c) == full


def test_ambiguous_first_name_does_not_link():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    c = Scope.conversation("conv-1")
    a = p.token("Anna Korhonen", label="PERSON", scope=c)
    b = p.token("Anna Lindqvist", label="PERSON", scope=c)
    bare = p.token("Anna", label="PERSON", scope=c)
    assert bare not in (a, b)


def test_linking_only_applies_in_conversation_scope():
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    full = p.token("Matti Virtanen", label="PERSON", scope=REL)
    assert p.token("Matti", label="PERSON", scope=REL) != full


# --- non-reversibility ----------------------------------------------------

_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def synthetic_hetus(n: int, seed: int = 6) -> list[str]:
    rng = random.Random(seed)
    out: set[str] = set()
    while len(out) < n:
        d, m, y = rng.randint(1, 28), rng.randint(1, 12), rng.randint(0, 99)
        sign = rng.choice("-+A")
        num = rng.randint(2, 899)
        base = f"{d:02d}{m:02d}{y:02d}"
        out.add(f"{base}{sign}{num:03d}{_HETU_CHECK[int(base + f'{num:03d}') % 31]}")
    return sorted(out)


def test_candidate_hashing_of_10k_hetus_recovers_no_tokens():
    hetus = synthetic_hetus(10_000)
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY), recipient="uni")
    tokens = {p.token(h, label="NATIONAL_ID", scope=REL) for h in hetus}
    assert len(tokens) == 10_000

    def forms(h: str):
        n = normalise(h, "NATIONAL_ID")
        yield from (h, h.lower(), n)
        for kind, sid in (("release", "0123456789abcdef"),):
            yield f"pets-release/pseudonym/v1\x00{kind}\x00{sid}\x00NATIONAL_ID\x00{n}"

    # an attacker compares full digests and digest-length prefixes of tokens
    prefixes = {32: {t[:32] for t in tokens}, 40: {t[:40] for t in tokens}, 64: tokens}
    recovered = 0
    for h in hetus:
        for f in forms(h):
            b = f.encode()
            for algo in (hashlib.md5, hashlib.sha1, hashlib.sha256):
                hx = algo(b).hexdigest()
                if hx in prefixes[len(hx)]:
                    recovered += 1
    assert recovered == 0


# --- follow-up #42 ---------------------------------------------------------


@pytest.mark.parametrize(
    "a,b",
    [
        ("Thoresen", "Thorenen"),
        ("Mathiesen", "Mathienen"),
        ("Andersen", "Andernen"),
        ("Petersen", "Peternen"),
        ("Mikkelsen", "Mikkelnen"),
    ],
)
def test_germanic_sen_surnames_are_not_turned_into_nen_names(a, b):
    assert normalise(a, "PERSON") == a.casefold()
    assert normalise(a, "PERSON") != b.casefold()


def test_finnish_nen_inflections_still_return_to_nominative():
    for form, nom in [
        ("Virtasen", "virtanen"),
        ("Korhosen", "korhonen"),
        ("Hämäläisen", "hämäläinen"),
        ("Mäkiselle", "mäkinen"),
        ("Koskiselta", "koskinen"),
    ]:
        assert normalise(form, "PERSON") == nom


@pytest.mark.parametrize(
    "a,b",
    [
        ("040 123 4567 x12", "0401234567"),
        ("+358 40 123 4567 ext. 99", "0401234567"),
        ("0401234567x5", "+358401234567"),
        ("+46 70 123 45 67 extension 3", "+46701234567"),
        ("040-1234567 EXT 2", "0401234567"),
    ],
)
def test_phone_extension_is_not_part_of_the_number(a, b):
    assert normalise(a, "PHONE") == normalise(b, "PHONE")


def test_spoken_six_is_not_an_extension():
    assert normalise("zero four zero six", "PHONE") == "+358406"


@pytest.mark.parametrize("where", ["value", "scope"])
def test_lone_surrogate_gives_content_free_value_error(where):
    bad = "ab\ud800cd"
    p = pseudonymiser_for(MasterKey.from_text(TEST_KEY))
    with pytest.raises(ValueError) as ei:
        if where == "value":
            p.token(bad, label="EMAIL", scope=REL)
        else:
            p.token("x", label="EMAIL", scope=Scope.conversation(bad))
    assert "ud800" not in str(ei.value).lower() and "ab" not in str(ei.value)
    assert not isinstance(ei.value, UnicodeError)
    assert ei.value.__cause__ is None and ei.value.__context__ is None


def test_secret_key_eq_and_hash_are_consistent():
    from pets_release.pseudonym.keys import MasterKey as MK
    from pets_release.pseudonym.keys import SecretKey

    m = MK(b"k" * 32)
    a, b = SecretKey(b"k" * 32, "x"), SecretKey(b"k" * 32, "y")
    assert (a == b) and hash(a) == hash(b)
    assert hash(m) == hash(SecretKey(b"k" * 32, "z"))
