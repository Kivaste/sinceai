"""compute_signature accepts raw key bytes (fixture path) or an opaque key object exposing hmac_sha256()."""

import hashlib
import hmac

import pytest

from pets_release.manifest import compute_signature, signing_bytes


class OpaqueKey:
    """Duck-typed stand-in for ticket 06's SecretKey: no bytes attribute is exposed."""

    __slots__ = ("_k",)

    def __init__(self, k: bytes):
        self._k = k

    def hmac_sha256(self, data: bytes) -> bytes:
        return hmac.new(self._k, data, hashlib.sha256).digest()

    def key_id(self) -> str:
        return "0123456789abcdef"


def test_opaque_key_object_gives_same_signature_as_its_bytes(m):
    raw = b"k" * 32
    expected = hmac.new(raw, signing_bytes(m), hashlib.sha256).hexdigest()
    assert compute_signature(m, OpaqueKey(raw)) == expected
    assert compute_signature(m, raw) == expected


def test_signature_ignores_existing_signature_field(m):
    key = OpaqueKey(b"k" * 32)
    before = compute_signature(m, key)
    m["signature"]["value"] = "f" * 64
    assert compute_signature(m, key) == before


@pytest.mark.parametrize("bad", ["a-string-key", None, 12, object()])
def test_unusable_key_is_rejected(m, bad):
    with pytest.raises(TypeError):
        compute_signature(m, bad)


def test_key_object_returning_non_bytes_is_rejected(m):
    class Bad:
        def hmac_sha256(self, data):
            return "deadbeef"

    with pytest.raises(TypeError):
        compute_signature(m, Bad())
