"""Value validators for structured labels. Pure functions on normalised strings.

This is the redactor's own implementation; the gate (``checks/text/``) has an
independent one and the two never share code.
"""

from __future__ import annotations

import ipaddress
import re

_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"
_HETU_RE = re.compile(r"(\d{6})([-+A-FU-Y])(\d{3})([0-9A-Y])")
_IBAN_LEN = {"FI": 18, "SE": 24, "EE": 20, "DE": 22, "NO": 15, "DK": 18, "GB": 22, "AX": 18}


def hetu_valid(s: str) -> bool:
    """Finnish personal identity code: ddmmyyCnnnX with mod-31 check character."""
    m = _HETU_RE.fullmatch(s.upper())
    if not m:
        return False
    dd, mm = int(m.group(1)[:2]), int(m.group(1)[2:4])
    if not (1 <= dd <= 31 and 1 <= mm <= 12):
        return False
    n = int(m.group(1) + m.group(3))
    return _HETU_CHECK[n % 31] == m.group(4)


def iban_valid(s: str) -> bool:
    s = s.upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    want = _IBAN_LEN.get(s[:2])
    if want is not None and len(s) != want:
        return False
    moved = s[4:] + s[:4]
    digits = "".join(str(int(c, 36)) for c in moved)
    return int(digits) % 97 == 1


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_iin_plausible(digits: str) -> bool:
    """Major card schemes by leading digits (Visa, Mastercard, Amex, Discover/UnionPay, JCB, Diners)."""
    return bool(re.match(r"4|5[1-5]|2[2-7]|3[47]|3[05689]|6", digits))


def ipv4_personal(s: str) -> bool:
    """A public, assignable IPv4 address (denylist: RFC1918, loopback, link-local, unspecified, broadcast,
    multicast/reserved)."""
    parts = s.split(".")
    if len(parts) != 4 or any(not p.isdigit() or len(p) > 3 or int(p) > 255 for p in parts):
        return False
    if any(len(p) > 1 and p.startswith("0") for p in parts):
        return False
    ip = ipaddress.IPv4Address(s)
    # 100.64.0.0/10 (carrier-grade NAT) is deliberately allowed: it is assigned per subscriber.
    return not (
        ipv4_denylisted(s) or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved
    )


def ipv4_denylisted(s: str) -> bool:
    """RFC1918 or loopback (the over-redaction denylist the spec names)."""
    try:
        ip = ipaddress.IPv4Address(s)
    except ValueError:
        return False
    return ip.is_loopback or any(
        ip in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )
