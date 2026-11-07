"""Review regressions (ticket 05, review 1): split positions, spelled domains, lexicon binding.

Identifiers are textbook test values (Visa test card, DVV example HETU, IBAN example).
"""
import json

import pytest

C = "customer"
A = "agent"
CARD = ["four"] + ["one"] * 15
HETU = "yksi kolme yksi nolla viisi kaksi viiva kolme nolla kahdeksan T".split()
PHONE = "nolla neljä nolla yksi kaksi kolme neljä viisi kuusi seitsemän".split()


def _splits(words, name):
    """Every split position of a spoken identifier across two turns (after each word)."""
    return [(name, " ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]


SPLITS = (
    _splits(CARD, "text.payment-cards")
    + _splits(HETU, "text.national-ids")
    + _splits(PHONE, "text.phones")
    + [
        ("text.payment-cards", "card 4", "111 1111 1111 1111"),          # after first digit
        ("text.payment-cards", "card 4111 11", "11 1111 1111"),          # mid-group
        ("text.payment-cards", "card 4111 1111 dash", "1111 1111"),      # at a spoken separator
        ("text.payment-cards", "card four one one one", "dash one one one one one one one one one one one one"),
        ("text.national-ids", "it is 1", "31052-308T"),
        ("text.national-ids", "it is 131052 viiva", "308T"),
    ]
)


@pytest.mark.parametrize("name,first,second", SPLITS)
def test_identifier_split_at_any_position_is_refused(gate, release, contract, name, first, second):
    folder = release([[(C, first), (C, second)]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1, (first, second)
    assert rec["violations"][0]["locations"] == [0, 1]


@pytest.mark.parametrize("name,first,second", SPLITS[:3])
def test_split_around_backchannel_is_refused(gate, release, contract, name, first, second):
    folder = release([[(C, first), (A, "ok"), (C, second)]])
    rec = gate(name, folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


@pytest.mark.parametrize("turns", [
    ["m a t t i at e x a m p l e dot com"],
    ["matti at e x a m p l e dot c o m"],
    ["m a t t i at e x a", "m p l e dot com"],
    ["matti at example", "dot c o m"],
    ["matti dot meikalainen at", "e x a m p l e piste fi"],
])
def test_spelled_domain_email_is_refused(gate, release, contract, turns):
    folder = release([[(C, t) for t in turns]])
    rec = gate("text.emails", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1, turns


@pytest.mark.parametrize("text", ["write to info@kesä.fi", "it is info at kesä dot fi"])
def test_email_with_nordic_letters_is_refused(gate, release, contract, text):
    folder = release([[(C, text)]])
    rec = gate("text.emails", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1


@pytest.mark.parametrize("turns", [
    ["F I 2 1 1 2 3 4 5 6 0 0 0 0 0 7 8 5"],
    ["F I kaksi yksi yksi kaksi kolme neljä viisi kuusi nolla nolla nolla nolla nolla seitsemän kahdeksan viisi"],
    ["iban F I 2 1 1 2 3 4", "5 6 0 0 0 0 0 7 8 5"],
])
def test_letter_by_letter_iban_is_refused(gate, release, contract, turns):
    folder = release([[(C, t) for t in turns]])
    rec = gate("text.ibans", folder, contract())
    assert rec["status"] == "fail" and rec["hits"] == 1, turns


# ---------------------------------------------------------------- lexicon binding


def _write_manifest(folder, lexicon_digests):
    bindings = {"files": {}}
    if lexicon_digests is not None:
        bindings["lexiconDigests"] = lexicon_digests
    (folder / "privacy_manifest.json").write_text(json.dumps({"bindings": bindings}), encoding="utf-8")


def _digest():
    from pets_release.checks import text

    return text.lexicon_digest()


@pytest.mark.parametrize("digests", [None, {}, {"other": "0" * 64}, {"gate-health": "0" * 64}])
def test_verify_requires_matching_health_lexicon_binding(gate, release, contract, digests):
    folder = release([[(C, "my invoice is wrong")]])
    _write_manifest(folder, digests)
    rec = gate("text.health", folder, contract(), {"phase": "verify"})
    assert rec["status"] == "error"


def test_verify_without_manifest_is_an_error(gate, release, contract):
    folder = release([[(C, "my invoice is wrong")]])
    rec = gate("text.health", folder, contract(), {"phase": "verify"})
    assert rec["status"] == "error"


def test_verify_default_phase_requires_binding(gate, release, contract):
    from pets_release.checks import run_checks
    from pets_release.checks.registry import all_checks

    folder = release([[(C, "my invoice is wrong")]])
    chk = [c for c in all_checks() if c.name == "text.health"]
    rec = run_checks(folder, contract(), {}, checks=chk).records[0]
    assert rec.status == "error"


def test_verify_with_matching_binding_passes(gate, release, contract):
    folder = release([[(C, "my invoice is wrong")]])
    _write_manifest(folder, {"gate-health": _digest()})
    rec = gate("text.health", folder, contract(), {"phase": "verify"})
    assert rec["status"] == "pass"


def test_gate_phase_without_manifest_uses_bundled_lexicon(gate, release, contract):
    folder = release([[(C, "my invoice is wrong")]])
    rec = gate("text.health", folder, contract(), {"phase": "gate"})
    assert rec["status"] == "pass"


@pytest.mark.parametrize("digests", [None, {}, {"gate-health": "0" * 64}])
def test_gate_phase_manifest_in_context_must_bind_lexicon(gate, release, contract, digests):
    folder = release([[(C, "my invoice is wrong")]])
    bindings = {} if digests is None else {"lexiconDigests": digests}
    rec = gate("text.health", folder, contract(), {"phase": "gate", "manifest": {"bindings": bindings}})
    assert rec["status"] == "error"
