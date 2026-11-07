"""Follow-up #47 edge cases for the text checks. Synthetic, textbook values only."""
import csv

import pytest

C = "customer"


def _one(release, text):
    return release([[(C, text)]])


@pytest.mark.parametrize("text", [
    "call 040 1234567 or 050 7654321 today",
    "numbers 0401234567 0507654321",
    "reach me on +358 40 1234567 +358 50 7654321",
])
def test_two_space_separated_phone_numbers_are_detected_as_two(gate, release, contract, text):
    rec = gate("text.phones", _one(release, text), contract())
    assert rec["status"] == "fail"
    assert rec["hits"] >= 1
    # the single-number detector must still work on each number alone
    for single in ("040 1234567", "+358 50 7654321"):
        assert gate("text.phones", _one(release, f"call {single}"), contract())["status"] == "fail"


def test_two_numbers_both_found_by_the_detector():
    from pets_release.checks.text import _detectors as d

    text = "call 040 1234567 050 7654321 now"
    hits = d.phones(text)
    assert [text[a:b] for a, b in hits] == ["040 1234567", "050 7654321"]


def test_over_long_digit_run_is_still_not_a_phone():
    from pets_release.checks.text import _detectors as d

    assert d.phones("order 123456789012345678 shipped") == []


@pytest.mark.parametrize("plate", ["abc-123", "Abc-123"])
def test_lower_and_mixed_case_plates_are_detected(gate, release, contract, plate):
    rec = gate("text.plates", _one(release, f"the car {plate} was parked"), contract())
    assert rec["status"] == "fail"


def test_denied_plate_words_stay_denied_in_any_case(gate, release, contract):
    assert gate("text.plates", _one(release, "see iso-9 and ISO-9"), contract())["status"] == "pass"


def test_password_symbol_before_sentence_end_counts_as_secret_like():
    from pets_release.checks.text import _detectors as d

    assert d.secrets("my password is Kissa!") != []
    # a sentence period is not a symbol (no copula, so a plain word needs a symbol to count; #53 makes
    # "password is <word>" a hit on its own)
    assert d.secrets("my password kissa.") == []


def test_pin_followed_by_exclamation_is_still_a_pin():
    from pets_release.checks.text import _detectors as d

    assert d.secrets("my pin is 4821!") != []


def test_non_numeric_turn_order_is_an_error(gate, tmp_path, contract):
    folder = tmp_path / "rel"
    folder.mkdir()
    with open(folder / "turns.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["turn_id", "conversation_id", "seq", "speaker", "text"])
        w.writerow(["T1", "C1", "first", "customer", "hello"])
        w.writerow(["T2", "C1", "2", "agent", "hi"])
    rec = gate("text.phones", folder, contract())
    assert rec["status"] == "error"


def test_sparse_undeclared_free_text_column_is_an_error(gate, release, contract):
    wordy = "my number is written here in this long sentence"
    convs = [[(C, wordy)] if i < 3 else [(C, "ok")] for i in range(30)]  # 10% wordy
    c = contract()
    c["files"]["turns.csv"]["columns"]["text"] = {"form": ".*", "params": {}}
    assert gate("text.phones", release(convs), c)["status"] == "error"


def test_single_wordy_undeclared_cell_is_not_an_error(gate, release, contract):
    convs = [[(C, "ok")] for _ in range(30)] + [[(C, "a b c d e f g h")]]
    c = contract()
    c["files"]["turns.csv"]["columns"]["text"] = {"form": ".*", "params": {}}
    assert gate("text.phones", release(convs), c)["status"] != "error"
