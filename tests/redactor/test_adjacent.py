"""One run must yield every identifier in it (review r4). Synthetic/public example values only."""

from __future__ import annotations

import itertools

import pytest

from pets_release.redactor import StructuredPass, Turn, redact_conversation

# Labels that need no cue. ACCOUNT_NUMBER, SECRET and USERNAME are cue-only by design and are
# covered by their own cue tests.
SAMPLES = {
    "NATIONAL_ID": "131052-308T",
    "IBAN": "FI21 1234 5600 0007 85",
    "PAYMENT_CARD": "4111 1111 1111 1111",
    "DEVICE_ID": "490154203237518",
    "PHONE": "040 123 4567",
    "EMAIL": "maija.m@posti.example",
    "IP_ADDRESS": "100.72.13.5",
    "PROPERTY_ID": "123-456-7-89",
    "URL": "https://pay.example/lasku?id=123456",
    "LICENSE_PLATE": "XYZ-123",
}


def spans(text):
    r = redact_conversation("c", [Turn("t0", text, "customer", "1")], passes=[StructuredPass()])
    return [(s["start"], s["end"], s["label"]) for s in r.spans]


@pytest.mark.parametrize("a,b", list(itertools.permutations(SAMPLES, 2)), ids=lambda x: x)
def test_two_adjacent_identifiers_in_one_run_are_both_redacted(a, b):
    va, vb = SAMPLES[a], SAMPLES[b]
    text = f"{va} {vb}"
    assert spans(text) == [(0, len(va), a), (len(va) + 1, len(text), b)]


def test_hetu_next_to_a_space_separated_number():
    t = "131052-308T 12"
    assert spans(t) == [(0, 11, "NATIONAL_ID")]
    u = "kohta 7 131052-308T"
    assert spans(u) == [(8, len(u), "NATIONAL_ID")]


def test_iban_followed_by_phone_in_one_run():
    t = "FI21 1234 5600 0007 85 040 123 4567"
    assert spans(t) == [(0, 22, "IBAN"), (23, len(t), "PHONE")]


def test_national_and_international_phone_forms_share_a_placeholder():
    r = redact_conversation("c", [Turn("t0", "040 123 4567", "customer", "1"),
                                  Turn("t1", "+358 40 123 4567", "customer", "2")], passes=[StructuredPass()])
    assert [s["placeholder"] for s in r.spans] == ["[PHONE_1]", "[PHONE_1]"]
