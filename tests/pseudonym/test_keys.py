"""Key custody, HKDF derivation and the release-scope ID. Synthetic keys only."""

import base64
import hashlib
import logging
import pickle

import pytest

from pets_release.pseudonym import (
    KeyConfigError,
    MasterKey,
    Scope,
    hkdf_sha256,
    manifest_signing_key,
    pseudonymiser_for,
    recipient_key,
    release_scope_id,
)

TEST_KEY = "synthetic-test-key-0123456789abcdef-not-real"
D1 = "a" * 64
D2 = "b" * 64


# --- master key from the environment ---------------------------------------


def test_key_from_env_requires_at_least_32_chars():
    with pytest.raises(KeyConfigError):
        MasterKey.from_env({})
    with pytest.raises(KeyConfigError):
        MasterKey.from_env({"PETS_HMAC_KEY": "x" * 31})
    MasterKey.from_env({"PETS_HMAC_KEY": "x" * 32})


def test_key_from_env_reads_process_environment(monkeypatch):
    monkeypatch.setenv("PETS_HMAC_KEY", TEST_KEY)
    assert MasterKey.from_env() == MasterKey.from_text(TEST_KEY)


# --- HKDF (RFC 5869 test vectors) -----------------------------------------


def test_hkdf_matches_rfc5869_case_1():
    okm = hkdf_sha256(
        bytes([0x0B] * 22),
        info=bytes(range(0xF0, 0xFA)),
        length=42,
        salt=bytes(range(0x0D)),
    )
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
        "34007208d5b887185865"
    )


def test_hkdf_matches_rfc5869_case_3_empty_salt_and_info():
    okm = hkdf_sha256(bytes([0x0B] * 22), info=b"", length=42)
    assert okm.hex() == (
        "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d"
        "9d201395faa4b61a96c8"
    )


def test_recipient_and_signing_keys_follow_the_pinned_derivation():
    master = MasterKey.from_text(TEST_KEY)
    ikm = TEST_KEY.encode()
    msg = b"probe"
    import hmac as _h

    expected_r = _h.new(hkdf_sha256(ikm, info=b"uni"), msg, hashlib.sha256).digest()
    expected_s = _h.new(
        hkdf_sha256(ikm, info=b"manifest-signature"), msg, hashlib.sha256
    ).digest()
    assert recipient_key(master, "uni").hmac_sha256(msg) == expected_r
    assert manifest_signing_key(master).hmac_sha256(msg) == expected_s
    assert expected_r != expected_s


def test_recipient_id_cannot_collide_with_signing_key():
    master = MasterKey.from_text(TEST_KEY)
    with pytest.raises(ValueError):
        recipient_key(master, "manifest-signature")
    with pytest.raises(ValueError):
        recipient_key(master, "")


# --- release-scope ID -----------------------------------------------------


def test_release_scope_id_is_first_16_hex_of_sha256_of_canonical_json():
    canonical = (
        '{"inputs":{"ed_visits":"' + D1 + '","lab_results":"' + D2 + '"},'
        '"recipient":"uni","scenario":"HEALTH-S1","toolRevision":"rev1"}'
    )
    expected = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    got = release_scope_id(
        scenario="HEALTH-S1",
        recipient="uni",
        input_digests={"lab_results": D2, "ed_visits": D1},
        tool_revision="rev1",
    )
    assert got == expected


def test_release_scope_id_is_stable_and_changes_with_any_input():
    base = {
        "scenario": "HEALTH-S1",
        "recipient": None,
        "input_digests": {"t": D1},
        "tool_revision": "r",
    }
    rid = release_scope_id(**base)
    assert rid == release_scope_id(**dict(base))
    variants = [
        dict(base, scenario="CS-S1"),
        dict(base, recipient="uni"),
        dict(base, input_digests={"t": D2}),
        dict(base, input_digests={"t": D1, "u": D2}),
        dict(base, input_digests={"u": D1}),
        dict(base, tool_revision="r2"),
    ]
    ids = {release_scope_id(**v) for v in variants}
    assert rid not in ids and len(ids) == len(variants)


def test_release_scope_id_rejects_non_digest_inputs():
    with pytest.raises(ValueError):
        release_scope_id(
            scenario="S",
            recipient=None,
            input_digests={"t": "nothex"},
            tool_revision="r",
        )
    with pytest.raises(ValueError):
        release_scope_id(
            scenario="S", recipient=None, input_digests={}, tool_revision="r"
        )


# --- the key never leaks ----------------------------------------------------


def _key_forms(raw: bytes) -> list[str]:
    return [
        raw.hex(),
        raw.hex().upper(),
        base64.b64encode(raw).decode(),
        base64.urlsafe_b64encode(raw).decode().rstrip("="),
    ]


def test_key_never_appears_in_returned_structures_logs_or_exceptions(caplog):
    caplog.set_level(logging.DEBUG)
    master = MasterKey.from_text(TEST_KEY)
    derived = [recipient_key(master, "uni"), manifest_signing_key(master)]
    raw_keys = [TEST_KEY.encode()] + [
        hkdf_sha256(TEST_KEY.encode(), info=i) for i in (b"uni", b"manifest-signature")
    ]
    forbidden = [TEST_KEY] + [f for r in raw_keys for f in _key_forms(r)]

    texts: list[str] = []
    p = pseudonymiser_for(master, recipient="uni")
    scope = Scope.release("0123456789abcdef")
    texts += [p.token(f"V{i}", label="RECORD_KEY", scope=scope) for i in range(200)]
    texts += [repr(master), str(master), repr(p), repr(scope)] + [
        repr(k) for k in derived
    ]
    texts += [k.key_id() for k in [master, *derived]]
    texts.append(
        release_scope_id(
            scenario="S", recipient="uni", input_digests={"t": D1}, tool_revision="r"
        )
    )

    def capture(fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - the text is what we scan
            texts.append(f"{type(e).__name__}: {e!s} {e!r}")
        else:
            raise AssertionError("expected an exception")

    capture(lambda: pickle.dumps(master))
    capture(lambda: pickle.dumps(p))
    capture(lambda: pickle.dumps(derived[0]))
    capture(lambda: MasterKey.from_text(TEST_KEY[:31]))
    capture(lambda: MasterKey.from_env({"PETS_HMAC_KEY": TEST_KEY[:20]}))
    capture(lambda: p.token("bad\x00value", label="RECORD_KEY", scope=scope))
    capture(lambda: recipient_key(master, "manifest-signature"))
    texts.append(caplog.text)

    blob = "\n".join(texts)
    for f in forbidden:
        assert f not in blob
    # the failing short-key text itself must not be echoed either
    assert TEST_KEY[:20] not in blob
