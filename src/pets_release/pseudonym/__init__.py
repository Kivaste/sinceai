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
    p = pseudonymiser_for(master, recipient=None | "id",
                          phone_country="358")   # default FI, see normalise
    p.token(value, label=RECORD_KEY, scope=Scope.release(rsid))     # 64-hex
    p.token(name, label="PERSON", scope=Scope.conversation(conv_id))

    sk = manifest_signing_key(master)      # SecretKey
    sk.hmac_sha256(canonical_bytes); sk.key_id()   # 16-hex public key ID

Pinned token format (5 NUL-separated UTF-8 fields; this deliberately adds the
scope kind to the spec's 4 so a conversation, release and recipient scope with
equal IDs can never collide)::

    token = hex(HMAC-SHA256(key, DOMAIN \\0 scope.kind \\0 scope.scope_id
                                  \\0 label \\0 normalise(value, label)))
    DOMAIN = "pets-release/pseudonym/v1"; scope.kind in
    {"conversation", "release", "recipient"}

No field may contain NUL (ValueError). Pass raw values: ``token`` normalises
internally; do not pre-normalise. Empty or whitespace-only RECORD_KEY and
NATIONAL_ID values are refused (content-free ValueError). ``key`` is
HKDF-SHA256(master, info=recipient ID) when a recipient is given, else the
master key. Every key, incl. ``MasterKey(bytes)``, must be >= 32 bytes.
The manifest signing key is
HKDF-SHA256(master, info="manifest-signature"); that recipient ID is reserved.

Labels: the 20 span labels plus ``RECORD_KEY`` (exact match, for table keys
such as visit or lab IDs). Use one Pseudonymiser per run: with label PERSON in
a conversation scope it links, to names already seen in that conversation
only, a multi-letter Finnish case form (Annalle -> Anna) and a bare first name
to the one full name with that first name (in-memory table only). Linking is
order-dependent and deterministic; see ``core.Pseudonymiser._link`` and
``normalise`` for what is and is not covered.

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
