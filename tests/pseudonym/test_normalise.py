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
            ],
        ),
        (
            "PHONE",
            [
                "+46 70 123 45 67",
                "070-1234567",
                "noll sju noll ett två tre fyra fem sex sju",
            ],
        ),
        (
            "PAYMENT_CARD",
            ["4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"],
        ),
        ("IBAN", ["FI21 1234 5600 0007 85", "fi2112345600000785"]),
        ("EMAIL", [" Anna.Example@Example.FI ", "anna.example@example.fi"]),
        ("PERSON", ["Anna", "Annalle", "Annan", "annas", "ANNA"]),
        ("PERSON", ["Matti Virtanen", "Matti Virtasen", "matti  virtaselle"]),
        ("PERSON", ["Erik", "Eriks"]),
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
    ],
)
def test_distinct_values_stay_distinct(label, a, b):
    assert tok(a, label) != tok(b, label)


def test_normalise_is_public_and_label_aware():
    assert normalise("040-123 4567", "PHONE") == "0401234567"
    assert normalise("Virtaselle", "PERSON") == normalise("Virtanen", "PERSON")
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
