"""Keyed pseudonyms, key derivation and the release-scope ID (ticket 06).

Interface for transforms (07), redactor (12) and writer (16)::

    from pets_release.pseudonym import (
        MasterKey, Scope, pseudonymiser_for, release_scope_id,
        manifest_signing_key, KeyConfigError, RECORD_KEY,
    )

    master = MasterKey.from_env()          # PETS_HMAC_KEY, >= 32 chars,
                                           # else KeyConfigError (CLI: exit 2)
    rsid = release_scope_id(scenario=..., recipient=None | "id",
                            input_digests={table: sha256hex}, tool_revision=...)
    p = pseudonymiser_for(master, recipient=None | "id")
    p.token(value, label=RECORD_KEY, scope=Scope.release(rsid))     # 64-hex
    p.token(name, label="PERSON", scope=Scope.conversation(conv_id))

    sk = manifest_signing_key(master)      # SecretKey
    sk.hmac_sha256(canonical_bytes); sk.key_id()   # 16-hex public key ID

Token = hex(HMAC-SHA256(key, NUL-join(DOMAIN, scope kind, scope ID, label,
normalise(value, label)))). ``key`` is HKDF-SHA256(master, info=recipient ID)
when a recipient is given, else the master key. The manifest signing key is
HKDF-SHA256(master, info="manifest-signature"); that recipient ID is reserved.

Labels: the 20 span labels plus ``RECORD_KEY`` (exact match, for table keys
such as visit or lab IDs). Use one Pseudonymiser per run: with label PERSON in
a conversation scope it links a bare first name to the one full name already
seen with that first name in that conversation (in-memory table only).

Keys never appear in ``repr``/``str``, cannot be pickled, and exceptions here
never contain keys or values.
"""

from .core import Pseudonymiser, Scope, pseudonymiser_for
from .keys import (
    KeyConfigError,
    MasterKey,
    SecretKey,
    hkdf_sha256,
    manifest_signing_key,
    recipient_key,
)
from .normalise import LABELS, RECORD_KEY, normalise
from .scope_id import release_scope_id

__all__ = [
    "LABELS",
    "RECORD_KEY",
    "KeyConfigError",
    "MasterKey",
    "Pseudonymiser",
    "Scope",
    "SecretKey",
    "hkdf_sha256",
    "manifest_signing_key",
    "normalise",
    "pseudonymiser_for",
    "recipient_key",
    "release_scope_id",
]
