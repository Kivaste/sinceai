"""Keyed pseudonyms: HMAC-SHA256 over NUL-separated fields."""

from __future__ import annotations

from dataclasses import dataclass

from .keys import MasterKey, SecretKey, recipient_key
from .normalise import normalise

DOMAIN = "pets-release/pseudonym/v1"
SCOPE_KINDS = ("conversation", "release", "recipient")


@dataclass(frozen=True, slots=True)
class Scope:
    kind: str
    scope_id: str

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise ValueError("unknown pseudonym scope kind")
        if not isinstance(self.scope_id, str) or not self.scope_id:
            raise ValueError("scope ID must be a non-empty string")
        if "\x00" in self.scope_id:
            raise ValueError("scope ID must not contain NUL")

    def __repr__(self) -> str:  # scope IDs may be data-derived (conversation)
        return f"Scope(kind={self.kind!r}, <id redacted>)"

    @classmethod
    def conversation(cls, conversation_id: str) -> Scope:
        return cls("conversation", conversation_id)

    @classmethod
    def release(cls, release_scope_id: str) -> Scope:
        return cls("release", release_scope_id)

    @classmethod
    def recipient(cls, recipient_id: str) -> Scope:
        return cls("recipient", recipient_id)


_AMBIGUOUS = object()


class Pseudonymiser:
    __slots__ = ("_key", "_links")

    def __init__(self, key: SecretKey) -> None:
        if not isinstance(key, SecretKey):
            raise TypeError("Pseudonymiser requires a SecretKey")
        self._key = key
        # conversation scope ID -> {first-name stem: full normalised name | _AMBIGUOUS}
        # in memory only; never serialised or returned.
        self._links: dict[str, dict[str, object]] = {}

    def _link(self, normalised: str, scope: Scope) -> str:
        links = self._links.setdefault(scope.scope_id, {})
        words = normalised.split(" ")
        if len(words) >= 2:
            seen = links.get(words[0])
            if seen is None:
                links[words[0]] = normalised
            elif seen != normalised:
                links[words[0]] = _AMBIGUOUS
            return normalised
        full = links.get(normalised)
        return full if isinstance(full, str) else normalised

    def __repr__(self) -> str:
        return "Pseudonymiser(<redacted>)"

    def __reduce__(self):
        raise TypeError("Pseudonymiser cannot be serialised")

    def token(self, value: str, *, label: str, scope: Scope) -> str:
        if not isinstance(scope, Scope):
            raise TypeError("scope must be a Scope")
        for name, field in (("value", value), ("label", label)):
            if not isinstance(field, str):
                raise TypeError(f"{name} must be a string")
            if "\x00" in field:
                raise ValueError(f"{name} must not contain NUL")
        norm = normalise(value, label)
        if label == "PERSON" and scope.kind == "conversation" and norm:
            norm = self._link(norm, scope)
        fields = (DOMAIN, scope.kind, scope.scope_id, label, norm)
        msg = "\x00".join(fields).encode("utf-8")
        return self._key.hmac_sha256(msg).hex()


def pseudonymiser_for(master: MasterKey, recipient: str | None = None) -> Pseudonymiser:
    """Pseudonymiser keyed by the recipient key, or by the master key if no recipient."""
    if recipient is None:
        return Pseudonymiser(master)
    return Pseudonymiser(recipient_key(master, recipient))
