"""Key custody and key derivation (HKDF-SHA256, RFC 5869).

Key material is held only inside :class:`SecretKey` objects. They never
expose the bytes through ``repr``/``str``, refuse pickling, and every
exception raised here is content-free (no key text, no values).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from collections.abc import Mapping

ENV_VAR = "PETS_HMAC_KEY"
MIN_KEY_CHARS = 32
MIN_KEY_BYTES = 32  # enforced on every SecretKey, incl. MasterKey(bytes)
MANIFEST_SIGNATURE_INFO = "manifest-signature"

_HASH_LEN = 32


class KeyConfigError(ValueError):
    """The master key is missing or too short. CLI maps this to exit 2."""


class SecretKey:
    """Opaque HMAC key. Use :func:`hmac_sha256`; never read the bytes."""

    __slots__ = ("_k", "_kind")

    def __init__(self, material: bytes, kind: str) -> None:
        if not isinstance(material, bytes) or len(material) < MIN_KEY_BYTES:
            raise KeyConfigError(f"key material must be at least {MIN_KEY_BYTES} bytes")
        self._k = material
        self._kind = kind

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self._kind!r}, <redacted>)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("key objects cannot be serialised")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretKey):
            return NotImplemented
        return hmac.compare_digest(self._k, other._k)

    def __hash__(self) -> int:
        # Must agree with __eq__, which compares key bytes only.
        return hash(self.hmac_sha256(b"pets-release/hash"))

    def hmac_sha256(self, message: bytes) -> bytes:
        return hmac.new(self._k, message, hashlib.sha256).digest()

    def scannable_forms(self) -> tuple[frozenset, frozenset]:
        """Package-internal, for ``producer.key-material`` only: the text forms of this key a leak could take.

        Returns ``(exact, lowercase)``: case-sensitive forms (base64 std/url, padded or not; UTF-8 text when
        decodable) and lower-case hex forms (matched case-insensitively), each also for the stripped bytes.
        The raw bytes never leave this class; callers must not print or store the forms.
        """
        exact, lower = set(), set()
        for b in {self._k, self._k.strip()}:
            std = base64.b64encode(b).decode()
            url = base64.urlsafe_b64encode(b).decode()
            exact |= {std, std.rstrip("="), url, url.rstrip("=")}
            try:
                exact.add(b.decode("utf-8"))
            except UnicodeDecodeError:
                pass
            lower.add(b.hex())
        return frozenset(f for f in exact if f), frozenset(f for f in lower if f)

    def key_id(self) -> str:
        """Public 16-hex identifier of this key (an HMAC, not a hash of it)."""
        return self.hmac_sha256(b"pets-release/key-id").hex()[:16]


class MasterKey(SecretKey):
    """The controller's master key (from ``PETS_HMAC_KEY``)."""

    __slots__ = ()

    def __init__(self, material: bytes) -> None:
        super().__init__(material, "master")

    @classmethod
    def from_text(cls, text: str) -> MasterKey:
        if not isinstance(text, str) or len(text) < MIN_KEY_CHARS:
            raise KeyConfigError(
                f"{ENV_VAR} must be at least {MIN_KEY_CHARS} characters"
            )
        # The codec error would carry the key text, so it must not even be
        # kept as __context__: raise only after leaving the except block.
        material = None
        try:
            material = text.encode("utf-8")
        except UnicodeError:
            pass
        if material is None:
            raise KeyConfigError(f"{ENV_VAR} must be valid UTF-8 text")
        return cls(material)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> MasterKey:
        env = os.environ if env is None else env
        text = env.get(ENV_VAR)
        if text is None:
            raise KeyConfigError(f"{ENV_VAR} is not set")
        return cls.from_text(text)


def hkdf_sha256(
    ikm: bytes, info: bytes, length: int = _HASH_LEN, salt: bytes = b""
) -> bytes:
    """RFC 5869 HKDF with SHA-256 (empty salt = HashLen zero bytes)."""
    if length <= 0 or length > 255 * _HASH_LEN:
        raise ValueError("invalid HKDF output length")
    prk = hmac.new(salt or b"\x00" * _HASH_LEN, ikm, hashlib.sha256).digest()
    okm, block = b"", b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


def _derive(master: MasterKey, info: str, kind: str) -> SecretKey:
    if not isinstance(master, MasterKey):
        raise TypeError("derivation requires a MasterKey")
    return SecretKey(hkdf_sha256(master._k, info.encode("utf-8")), kind)


def recipient_key(master: MasterKey, recipient_id: str) -> SecretKey:
    """HKDF-SHA256(master, info = recipient ID)."""
    if not isinstance(recipient_id, str) or not recipient_id.strip():
        raise ValueError("recipient ID must be a non-empty string")
    if "\x00" in recipient_id:
        raise ValueError("recipient ID must not contain NUL")
    if recipient_id == MANIFEST_SIGNATURE_INFO:
        raise ValueError("recipient ID is reserved")
    return _derive(master, recipient_id, "recipient")


def manifest_signing_key(master: MasterKey) -> SecretKey:
    """HKDF-SHA256(master, info = "manifest-signature")."""
    return _derive(master, MANIFEST_SIGNATURE_INFO, "manifest-signature")
