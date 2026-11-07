"""Behaviour of the pseudonymiser through its public interface.

All keys and values here are synthetic test material, never kit data.
"""

import re

from pets_release.pseudonym import MasterKey, Pseudonymiser, Scope, pseudonymiser_for

TEST_KEY = "synthetic-test-key-0123456789abcdef-not-real"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def make(key: str = TEST_KEY) -> Pseudonymiser:
    return Pseudonymiser(MasterKey.from_text(key))


def test_same_value_same_scope_gives_same_64_hex_token():
    p = make()
    scope = Scope.release("0123456789abcdef")
    a = p.token("V-0001", label="RECORD_KEY", scope=scope)
    b = make().token("V-0001", label="RECORD_KEY", scope=scope)
    assert HEX64.match(a)
    assert a == b


def test_different_scope_kind_or_id_or_label_gives_different_token():
    p = make()
    v = "V-0001"
    tokens = {
        p.token(v, label="RECORD_KEY", scope=Scope.release("0123456789abcdef")),
        p.token(v, label="RECORD_KEY", scope=Scope.release("fedcba9876543210")),
        p.token(v, label="RECORD_KEY", scope=Scope.conversation("0123456789abcdef")),
        p.token(v, label="RECORD_KEY", scope=Scope.recipient("0123456789abcdef")),
        p.token(v, label="PHONE", scope=Scope.release("0123456789abcdef")),
    }
    assert len(tokens) == 5


def test_nul_cannot_shift_field_boundaries():
    p = make()
    s = Scope.release("abc")
    try:
        p.token("x\x00y", label="RECORD_KEY", scope=s)
    except ValueError:
        pass
    else:
        raise AssertionError("NUL in value must be rejected")
    try:
        p.token("y", label="RECORD_KEY\x00x", scope=s)
    except ValueError:
        pass
    else:
        raise AssertionError("NUL in label must be rejected")


def test_two_recipient_keys_share_no_tokens():
    master = MasterKey.from_text(TEST_KEY)
    pa = pseudonymiser_for(master, recipient="uni-research-group")
    pb = pseudonymiser_for(master, recipient="llm-vendor")
    scope = Scope.release("0123456789abcdef")
    values = [f"V{i:06d}" for i in range(2000)]
    ta = {pa.token(v, label="RECORD_KEY", scope=scope) for v in values}
    tb = {pb.token(v, label="RECORD_KEY", scope=scope) for v in values}
    assert len(ta) == len(tb) == 2000
    assert ta.isdisjoint(tb)
    # and neither recipient shares tokens with the un-scoped master pseudonymiser
    tm = {
        pseudonymiser_for(master).token(v, label="RECORD_KEY", scope=scope)
        for v in values
    }
    assert tm.isdisjoint(ta) and tm.isdisjoint(tb)


def test_same_recipient_derivation_is_stable():
    master = MasterKey.from_text(TEST_KEY)
    scope = Scope.release("0123456789abcdef")
    a = pseudonymiser_for(master, recipient="r1").token(
        "V1", label="RECORD_KEY", scope=scope
    )
    b = pseudonymiser_for(MasterKey.from_text(TEST_KEY), recipient="r1").token(
        "V1", label="RECORD_KEY", scope=scope
    )
    assert a == b
