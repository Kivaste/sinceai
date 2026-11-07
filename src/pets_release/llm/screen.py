"""Value screen shared by the request and the dictionary metadata, plus the credential screen for drafts.

Content-free: functions answer yes/no and never return the matched text.
"""
from __future__ import annotations

import base64
import re

_VALUE_SHAPES = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"\b\d{6}[-+A-Fa-f]\d{3}[0-9A-Za-z]\b"),  # Finnish personal identity code shape
    re.compile(r"\d{9,}"),  # long digit run (phone, card, account)
    re.compile(r"\d(?:[ -]?\d){11,}"),  # spaced or dashed digit run (card, account)
    re.compile(r"\b[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]){11,30}\b"),  # IBAN shape
    re.compile(r"(?<!\w)\+\d[\d ()-]{6,}\d"),  # international phone
    re.compile(r"(?i)\b(?:https?://|ftp://|www\.)\S+"),  # URL
)
_CREDENTIAL_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"),  # JWT
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b[0-9a-fA-F]{40,}\b"),  # long hex (key material)
)
MIN_KEY_CHECK = 6


def has_value_shape(text: str) -> bool:
    return any(p.search(text) for p in _VALUE_SHAPES)


def key_forms(key: str) -> list[str]:
    raw = key.encode("utf-8")
    forms = {key, raw.hex(), raw.hex().upper(), base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()}
    forms |= {f.rstrip("=") for f in list(forms)}
    return sorted(f for f in forms if f)


def has_credential(strings: list[str], api_key: str = "") -> bool:
    """True if any string contains the API key (raw, hex, base64) or a credential-shaped token."""
    forms = key_forms(api_key) if len(api_key) >= MIN_KEY_CHECK else []
    for s in strings:
        if any(f in s for f in forms) or any(p.search(s) for p in _CREDENTIAL_SHAPES):
            return True
    return False
