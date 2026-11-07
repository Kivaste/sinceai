"""Recipient-ID validation (ticket 28). Synthetic values only."""

import pytest

from pets_release.recipient import RecipientError, validate_recipient_id


@pytest.mark.parametrize(
    "bad",
    ["", " ", "a b", "a\x00b", "x" * 65, "-lead", "manifest-signature", "default",
     "ä", "a/b", "a\n"],
)
def test_invalid_recipient_ids_are_refused(bad):
    with pytest.raises(RecipientError):
        validate_recipient_id(bad)


def test_non_string_recipient_is_refused():
    with pytest.raises(RecipientError):
        validate_recipient_id(None)  # type: ignore[arg-type]


def test_valid_recipient_id_is_returned_unchanged():
    assert validate_recipient_id("univ-helsinki.ed_2026") == "univ-helsinki.ed_2026"


def test_refusal_message_does_not_echo_the_id():
    with pytest.raises(RecipientError) as e:
        validate_recipient_id("bad id with space")
    assert "bad id" not in str(e.value)
