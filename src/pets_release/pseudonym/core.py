"""Keyed pseudonyms: HMAC-SHA256 over NUL-separated fields."""

from __future__ import annotations

from dataclasses import dataclass, field

from .keys import MasterKey, SecretKey, recipient_key
from .normalise import (
    CASE_ENDINGS,
    DEFAULT_PHONE_COUNTRY,
    MIN_BASE_NAME,
    RECORD_KEY,
    normalise,
)

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
# Values that must carry an identity; an empty one would share a valid token.
_NON_EMPTY_LABELS = frozenset({RECORD_KEY, "NATIONAL_ID"})


def _bases(word: str) -> set[str]:
    """Candidate base names of ``word`` under one CASE_ENDINGS suffix."""
    return {
        word[: -len(e)]
        for e in CASE_ENDINGS
        if word.endswith(e) and len(word) - len(e) >= MIN_BASE_NAME
    }


@dataclass(slots=True)
class _Conversation:
    """In-memory name table of one conversation scope; never serialised."""

    words: set[str] = field(default_factory=set)  # every name word seen
    fulls: set[str] = field(default_factory=set)  # every multi-word name seen
    first: dict[str, object] = field(default_factory=dict)  # first word -> full


class Pseudonymiser:
    __slots__ = ("_convs", "_key", "_phone_country")

    def __init__(
        self, key: SecretKey, *, phone_country: str = DEFAULT_PHONE_COUNTRY
    ) -> None:
        if not isinstance(key, SecretKey):
            raise TypeError("Pseudonymiser requires a SecretKey")
        normalise("0", "PHONE", phone_country=phone_country)  # validates
        self._key = key
        self._phone_country = phone_country
        self._convs: dict[str, _Conversation] = {}

    def _link(self, normalised: str, scope: Scope) -> str:
        """Conversation-scope PERSON linking (order-dependent, deterministic).

        - A word not seen before that equals a seen name word plus one
          CASE_ENDINGS suffix (exactly one such base) becomes that name.
        - In a multi-word name only the last word inflects, and it links only
          to a full name already seen with the same leading words.
        - A bare name then links to the one full name with that first word
          (none if two full names share it).
        """
        st = self._convs.setdefault(scope.scope_id, _Conversation())
        words = normalised.split(" ")
        if len(words) == 1:
            w = words[0]
            if w not in st.words:
                hits = _bases(w) & st.words
                if len(hits) == 1:
                    w = hits.pop()
            st.words.add(w)
            full = st.first.get(w)
            return full if isinstance(full, str) else w
        if normalised not in st.fulls:
            head = words[:-1]
            hits = {" ".join([*head, b]) for b in _bases(words[-1])} & st.fulls
            if len(hits) == 1:
                normalised = hits.pop()
                words = normalised.split(" ")
        st.fulls.add(normalised)
        st.words.update(words)
        seen = st.first.get(words[0])
        if seen is None:
            st.first[words[0]] = normalised
        elif seen != normalised:
            st.first[words[0]] = _AMBIGUOUS
        return normalised

    def __repr__(self) -> str:
        return "Pseudonymiser(<redacted>)"

    def __reduce__(self):
        raise TypeError("Pseudonymiser cannot be serialised")

    def token(self, value: str, *, label: str, scope: Scope) -> str:
        if not isinstance(scope, Scope):
            raise TypeError("scope must be a Scope")
        for name, fval in (("value", value), ("label", label)):
            if not isinstance(fval, str):
                raise TypeError(f"{name} must be a string")
            if "\x00" in fval:
                raise ValueError(f"{name} must not contain NUL")
        norm = normalise(value, label, phone_country=self._phone_country)
        if label in _NON_EMPTY_LABELS and not norm:
            raise ValueError(f"empty {label} value cannot be pseudonymised")
        if label == "PERSON" and scope.kind == "conversation" and norm:
            norm = self._link(norm, scope)
        fields = (DOMAIN, scope.kind, scope.scope_id, label, norm)
        msg = "\x00".join(fields).encode("utf-8")
        return self._key.hmac_sha256(msg).hex()


def pseudonymiser_for(
    master: MasterKey,
    recipient: str | None = None,
    *,
    phone_country: str = DEFAULT_PHONE_COUNTRY,
) -> Pseudonymiser:
    """Pseudonymiser keyed by the recipient key, else by the master key.

    ``phone_country``: country code (digits, no '+') given to domestic phone
    numbers; default "358" (FI).
    """
    key = master if recipient is None else recipient_key(master, recipient)
    return Pseudonymiser(key, phone_country=phone_country)
