"""Recipient-ID validation for ``run --recipient <id>`` (ticket 28).

``run`` calls :func:`validate_recipient_id` and then threads the ID through its
existing scope plumbing: the release scope ID (``manifest.release_scope_id``)
binds the recipient, the pseudonymiser key is HKDF-SHA256(master, info=ID)
(``pseudonym.pseudonymiser_for``), and the manifest records the ID in
``release.recipient``. Two recipients therefore share no tokens; within one
release every table uses the same key and scope, so joins survive.

``RecipientError`` is a usage error (exit 2). Messages never echo the ID.
"""

from __future__ import annotations

import re

from pets_release.pseudonym.keys import MANIFEST_SIGNATURE_INFO

# Same shape as ticket 02's check-name pattern, with upper case allowed.
_RECIPIENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# "manifest-signature": HKDF info of the signing key. "default": the manifest
# value of a release without --recipient (keyed by the master itself).
_RESERVED = frozenset({MANIFEST_SIGNATURE_INFO, "default"})


class RecipientError(ValueError):
    """Invalid recipient ID."""


def validate_recipient_id(recipient: str) -> str:
    if not isinstance(recipient, str) or not _RECIPIENT.fullmatch(recipient):
        raise RecipientError(
            "recipient ID must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}"
        )
    if recipient in _RESERVED:
        raise RecipientError("recipient ID is reserved")
    return recipient
