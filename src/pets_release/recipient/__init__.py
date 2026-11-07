"""Recipient wiring for ``run --recipient <id>`` (ticket 28).

Ticket 21 owns ``pets_release/run/``; it (or a follow-up) wires the flag by::

    from pets_release.recipient import release_scope, RecipientError

    rs = release_scope(master, scenario=..., recipient=args.recipient,  # None ok
                       input_digests=..., tool_revision=...)
    rs.pseudonymiser.token(v, label=RECORD_KEY, scope=rs.scope)  # table keys
    manifest["release"].update(rs.manifest_release_fields())     # recipient, releaseScopeId

``RecipientError`` is a usage error: the CLI exits 2.

Isolation: the pseudonymiser key is HKDF-SHA256(master, info=recipient ID) and
the release scope ID also binds the recipient, so two recipients share no
tokens; within one release every table uses the same key and scope, so joins
survive.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pets_release.pseudonym import (
    MasterKey,
    Pseudonymiser,
    Scope,
    pseudonymiser_for,
    release_scope_id,
)

# Same shape as ticket 02's check-name pattern, with upper case allowed.
_RECIPIENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_RESERVED = frozenset({"manifest-signature"})


class RecipientError(ValueError):
    """Invalid recipient ID. Messages never echo the value."""


def validate_recipient_id(recipient: str) -> str:
    if not isinstance(recipient, str) or not _RECIPIENT.fullmatch(recipient):
        raise RecipientError(
            "recipient ID must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}"
        )
    if recipient in _RESERVED:
        raise RecipientError("recipient ID is reserved")
    return recipient


@dataclass(frozen=True, slots=True)
class RecipientRelease:
    recipient: str | None
    release_scope_id: str
    pseudonymiser: Pseudonymiser
    scope: Scope

    def __repr__(self) -> str:
        return f"RecipientRelease(scope={self.release_scope_id})"

    def manifest_release_fields(self) -> dict[str, str | None]:
        """The recipient-dependent keys of the manifest's ``release`` record."""
        return {
            "recipient": self.recipient,
            "releaseScopeId": self.release_scope_id,
        }


def release_scope(
    master: MasterKey,
    *,
    scenario: str,
    recipient: str | None,
    input_digests: Mapping[str, str],
    tool_revision: str,
) -> RecipientRelease:
    if recipient is not None:
        validate_recipient_id(recipient)
    rsid = release_scope_id(
        scenario=scenario,
        recipient=recipient,
        input_digests=input_digests,
        tool_revision=tool_revision,
    )
    return RecipientRelease(
        recipient=recipient,
        release_scope_id=rsid,
        pseudonymiser=pseudonymiser_for(master, recipient=recipient),
        scope=Scope.release(rsid),
    )
