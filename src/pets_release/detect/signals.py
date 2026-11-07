"""Value validators and column-name tokens. Pure functions over strings; no I/O."""

from __future__ import annotations

import ipaddress
import re

HETU_CHARS = "0123456789ABCDEFHJKLMNPRSTUVWXY"
_HETU = re.compile(r"^(\d{2})(\d{2})(\d{2})([-+A-FU-Y])(\d{3})([0-9A-Y])$")
_EMAIL = re.compile(r"^[\w.+'-]+@[\w-]+(\.[\w-]+)+$")
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
_MAC = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
_HEX = re.compile(r"^[0-9a-fA-F]{32,64}$")
_PLATE = re.compile(r"^[A-ZÅÄÖ]{2,3}[- ]?\d{1,3}$")
_PHONE = re.compile(r"^(\+|00)?[\d][\d ()/-]{6,18}\d$")
_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)
_HOST = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_TS_ALT = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}[ T]\d{1,2}:\d{2}")
_DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_FI = re.compile(r"^\d{1,2}\.\d{1,2}\.(\d{4})$")
_ICD = re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,3})?$")
_IDLIKE = re.compile(r"^[A-Za-z]{1,6}[-_]?[A-Za-z0-9]{0,6}[-_]?\d{3,}$|^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
_NAME_WORD = r"[A-ZÅÄÖÉÜ][a-zåäöéüß'’-]+"
_PERSON = re.compile(rf"^{_NAME_WORD}( {_NAME_WORD}){{1,3}}$")
_STREET = re.compile(r"\b\d{1,4}(\s?[A-Za-z])?(\s?\d{1,3})?$")
STREET_WORDS = ("katu", "tie", "kuja", "polku", "gatan", "vägen", "väg", "street", "road", "tori", "ranta", "katu.")
_UA = re.compile(r"Mozilla/|Chrome/|Safari/|curl/", re.I)
_NUM = re.compile(r"^-?\d+([.,]\d+)?$")


def hetu(v: str) -> bool:
    m = _HETU.match(v)
    if not m:
        return False
    d, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mo <= 12):
        return False
    return HETU_CHARS[int(m.group(1) + m.group(2) + m.group(3) + m.group(5)) % 31] == m.group(6)


def hetu_shape(v: str) -> bool:
    """HETU layout with a plausible birth date, ignoring the check character."""
    m = _HETU.match(v)
    return bool(m) and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12


def email(v: str) -> bool:
    return bool(_EMAIL.match(v))


def iban(v: str) -> bool:
    s = v.replace(" ", "").upper()
    if not _IBAN.match(s):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def luhn(v: str) -> bool:
    s = v.replace(" ", "").replace("-", "")
    if not s.isdigit() or not 13 <= len(s) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(s)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def ipv4(v: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(v), ipaddress.IPv4Address) and v.count(".") == 3
    except ValueError:
        return False


def ipv6(v: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(v), ipaddress.IPv6Address)
    except ValueError:
        return False


def mac(v: str) -> bool:
    return bool(_MAC.match(v))


def hex_digest(v: str) -> bool:
    return bool(_HEX.match(v)) and any(c.isalpha() for c in v)


def plate(v: str) -> bool:
    return bool(_PLATE.match(v))


def phone(v: str) -> bool:
    if not _PHONE.match(v):
        return False
    digits = re.sub(r"\D", "", v)
    return 7 <= len(digits) <= 15 and (v.startswith(("+", "0")))


def url(v: str) -> bool:
    return bool(_URL.match(v))


def hostname(v: str) -> bool:
    return bool(_HOST.match(v)) and not _NUM.match(v) and not ipv4(v) and not email(v)


def user_agent(v: str) -> bool:
    return bool(_UA.search(v))


def timestamp(v: str) -> bool:
    return bool(_TS.match(v) or _TS_ALT.match(v))


_DATE_SLASH4 = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DATE_SLASH2 = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2})$")
_DATE_YMD_SLASH = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


def _valid_dm(a: int, b: int) -> bool:
    """Day-month in either order."""
    return (1 <= a <= 31 and 1 <= b <= 12) or (1 <= b <= 31 and 1 <= a <= 12)


def date_year(v: str) -> int | None:
    m = _DATE_ISO.match(v)
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
        return int(m.group(1))
    m = _DATE_YMD_SLASH.match(v)
    if m and _valid_dm(int(m.group(2)), int(m.group(3))):
        return int(m.group(1))
    m = _DATE_SLASH4.match(v)
    if m and _valid_dm(int(m.group(1)), int(m.group(2))):
        return int(m.group(3))
    m = _DATE_SLASH2.match(v)
    if m and _valid_dm(int(m.group(1)), int(m.group(2))):
        yy = int(m.group(3))
        return 2000 + yy if yy < 40 else 1900 + yy
    return None


def timestamp_year(v: str) -> int | None:
    if _TS.match(v):
        return int(v[:4])
    m = re.match(r"^\d{1,2}\.\d{1,2}\.(\d{4})", v)
    return int(m.group(1)) if m and _TS_ALT.match(v) else None


def icd10(v: str) -> bool:
    parts = [p.strip() for p in re.split(r"[|;,]", v) if p.strip()]
    return bool(parts) and all(_ICD.match(p) for p in parts)


def id_like(v: str) -> bool:
    return bool(_IDLIKE.match(v))


def person_name(v: str) -> bool:
    return bool(_PERSON.match(v)) and not street_address(v) and not any(
        w.lower().endswith(STREET_WORDS) for w in v.split()
    )


_POSTCODE_TOWN = re.compile(r",\s*\d{5}\s+\S+")


def street_address(v: str) -> bool:
    core = _POSTCODE_TOWN.sub("", v).strip()
    return bool(re.search(r"[A-Za-zÅÄÖåäö]{3}", core)) and bool(_STREET.search(core)) and any(
        w.lower().endswith(STREET_WORDS) for w in re.split(r"[\s,]+", core)
    )


_NUM_GROUPED = re.compile(r"^-?\d{1,3}([  ]\d{3})+([.,]\d+)?$")


def number(v: str) -> float | None:
    if _NUM_GROUPED.match(v):
        return float(re.sub(r"[  ]", "", v).replace(",", "."))
    if not _NUM.match(v):
        return None
    return float(v.replace(",", "."))


# --- column-name tokens ---------------------------------------------------------------------------------

_OBFUSCATED = re.compile(r"^(col|column|field|c|f|v|var|x|attr)?[_-]?\d{1,4}$", re.I)


def name_tokens(name: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", name)
    return [t for t in re.split(r"[^0-9A-Za-zåäöÅÄÖ]+", s.lower()) if t]


def obfuscated(name: str) -> bool:
    """Header carries no meaning: a bare index such as c07, field_12, 3."""
    return bool(_OBFUSCATED.match(name.strip()))
