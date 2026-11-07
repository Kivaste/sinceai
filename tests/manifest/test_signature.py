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


def test_release_scope_id_equals_ticket_06(m):
    from pets_release.manifest import release_scope_id
    from pets_release.pseudonym import release_scope_id as ticket06

    args = {"scenario": m["release"]["scenario"], "recipient": m["release"]["recipient"],
            "tool_revision": m["bindings"]["toolRevision"]}
    ours = release_scope_id(inputs=m["bindings"]["inputs"], **args)
    assert ours == ticket06(input_digests=m["bindings"]["inputs"], **args) == m["release"]["releaseScopeId"]


def test_signature_with_ticket_06_signing_key(m):
    from pets_release.pseudonym import MasterKey, manifest_signing_key

    sk = manifest_signing_key(MasterKey(b"m" * 40))
    assert compute_signature(m, sk) == sk.hmac_sha256(signing_bytes(m)).hex()


def test_key_object_returning_non_bytes_is_rejected(m):
    class Bad:
        def hmac_sha256(self, data):
            return "deadbeef"

    with pytest.raises(TypeError):
        compute_signature(m, Bad())
