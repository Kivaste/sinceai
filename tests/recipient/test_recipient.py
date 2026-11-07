"""Recipient wiring (ticket 28). Synthetic values only.

Seams: validate_recipient_id, release_scope (the object `run --recipient` uses).
"""

import secrets

import pytest

from pets_release.pseudonym import RECORD_KEY, MasterKey
from pets_release.recipient import (
    RecipientError,
    release_scope,
    validate_recipient_id,
)

DIGESTS = {"ed_visits": "a" * 64, "lab_results": "b" * 64}
IDS = [f"V{i:04d}" for i in range(200)]


def _master():
    return MasterKey.from_text(secrets.token_hex(32))


def _scope(master, recipient, digests=DIGESTS):
    return release_scope(
        master,
        scenario="HEALTH-S1",
        recipient=recipient,
        input_digests=digests,
        tool_revision="rev1",
    )


def _tokens(rs, values=IDS):
    return {rs.pseudonymiser.token(v, label=RECORD_KEY, scope=rs.scope) for v in values}


@pytest.mark.parametrize(
    "bad",
    ["", " ", "a b", "a\x00b", "x" * 65, "-lead", "manifest-signature", "ä", "a/b", "a\n"],
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


def test_two_recipients_share_zero_tokens():
    m = _master()
    assert _tokens(_scope(m, "alpha")).isdisjoint(_tokens(_scope(m, "beta")))


def test_joins_survive_within_one_recipient_release():
    m = _master()
    rs = _scope(m, "alpha")
    visits = [rs.pseudonymiser.token(v, label=RECORD_KEY, scope=rs.scope) for v in IDS]
    labs = [rs.pseudonymiser.token(v, label=RECORD_KEY, scope=rs.scope) for v in IDS[:50]]
    assert set(labs) <= set(visits)
    assert len(set(visits)) == len(IDS)


def test_same_recipient_same_inputs_is_deterministic():
    m = MasterKey.from_text("k" * 40)
    assert _tokens(_scope(m, "alpha")) == _tokens(_scope(m, "alpha"))


def test_no_recipient_differs_from_recipient_release():
    m = _master()
    assert _tokens(_scope(m, None)).isdisjoint(_tokens(_scope(m, "alpha")))


def test_manifest_record_has_exact_keys_and_scope_id():
    rs = _scope(_master(), "alpha")
    rec = rs.manifest_release_fields()
    assert set(rec) == {"recipient", "releaseScopeId"}
    assert rec["recipient"] == "alpha"
    assert len(rec["releaseScopeId"]) == 16


def test_manifest_record_for_no_recipient_is_null():
    assert _scope(_master(), None).manifest_release_fields()["recipient"] is None


def test_release_scope_id_differs_per_recipient():
    m = _master()
    a, b = _scope(m, "alpha"), _scope(m, "beta")
    assert a.release_scope_id != b.release_scope_id


def test_invalid_recipient_refused_by_release_scope():
    with pytest.raises(RecipientError):
        _scope(_master(), "bad id")


def test_repr_does_not_leak_the_key():
    text = secrets.token_hex(32)
    rs = _scope(MasterKey.from_text(text), "alpha")
    assert text not in repr(rs) and text not in str(rs)
