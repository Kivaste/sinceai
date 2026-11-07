"""Gate-side identifier detectors over normalised text. Independent of the redactor.

Each detector takes one string (a normalised view of a turn or of a joined window) and
returns a list of (start, end) character spans. Validators are checksum- or structure-based
where the label has one (HETU, Luhn, IBAN mod-97, IP parsing).
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

from ._normalise import SPOKEN_AT, SPOKEN_DOT

# ---------------------------------------------------------------- checksums


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def hetu_ok(birth: str, sign: str, serial: str, check: str) -> bool:
    dd, mm = int(birth[:2]), int(birth[2:4])
    if not (1 <= dd <= 31 and 1 <= mm <= 12):
        return False
    if sign.upper() not in "-+ABCDEFUVWXY":
        return False
    return _HETU_CHECK[int(birth + serial) % 31] == check.upper()


IBAN_LENGTHS = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GB": 22, "GI": 23,
    "GL": 18, "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28,
    "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27,
}


def iban_ok(compact: str) -> bool:
    s = compact[4:] + compact[:4]
    num = "".join(str(int(ch, 36)) for ch in s)
    return int(num) % 97 == 1


# ---------------------------------------------------------------- helpers

_RUN_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:[ \t]*-?[ \t]*\d+)*(?![A-Za-z0-9])")
_GROUP_RE = re.compile(r"\d+")


def _group_runs(text):
    for run in _RUN_RE.finditer(text):
        groups = [(run.start() + g.start(), run.start() + g.end(), g.group(0))
                  for g in _GROUP_RE.finditer(run.group(0))]
        yield run, groups


# ---------------------------------------------------------------- NATIONAL_ID

_HETU_RE = re.compile(
    r"(?<![0-9A-Za-z])((?:\d[ \t]*){6})([-+A-Fa-fU-Yu-y])[ \t]*((?:\d[ \t]*){3})([0-9A-Za-z])(?![0-9A-Za-z])"
)


def national_ids(text):
    hits = []
    for m in _HETU_RE.finditer(text):
        birth = re.sub(r"\s", "", m.group(1))
        serial = re.sub(r"\s", "", m.group(3))
        if hetu_ok(birth, m.group(2), serial, m.group(4)):
            hits.append((m.start(), m.end()))
    return hits


# ---------------------------------------------------------------- PAYMENT_CARD


def is_imei(digits: str) -> bool:
    """15 digits, Luhn-valid, not an Amex prefix (34/37): an IMEI rather than a card."""
    return len(digits) == 15 and digits[:2] not in ("34", "37") and luhn_ok(digits)


def payment_cards(text):
    hits = []
    for _run, groups in _group_runs(text):
        i = 0
        while i < len(groups):
            found = None
            for j in range(len(groups), i, -1):
                digits = "".join(g[2] for g in groups[i:j])
                if 13 <= len(digits) <= 19 and digits[0] in "23456" and luhn_ok(digits) \
                        and not is_imei(digits):
                    found = j
                    break
            if found:
                hits.append((groups[i][0], groups[found - 1][1]))
                i = found
            else:
                i += 1
    return hits


# ---------------------------------------------------------------- PHONE

_PHONE_RE = re.compile(
    r"(?<![\w+.,/])(\+[ \t]*)?\(?\d+\)?(?:[ \t]*-?[ \t]*\(?\d+\)?)*(?![\w/])"
)
_DATE_LIKE = re.compile(r"^\d{1,2}[-./ ]\d{1,2}[-./ ]\d{2,4}$")


def _overlaps_any(span, spans):
    return any(s < span[1] and span[0] < e for s, e in spans)


def phones(text):
    hits = []
    hetus = national_ids(text)
    for m in _PHONE_RE.finditer(text):
        if _overlaps_any(m.span(), hetus):
            continue
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if _DATE_LIKE.match(raw.strip()):
            continue
        ok = False
        if m.group(1):
            ok = 8 <= len(digits) <= 15
        elif digits.startswith("00"):
            ok = 10 <= len(digits) <= 15
        elif re.fullmatch(r"0[1-9]\d{5,9}", digits):
            ok = True
        if ok:
            hits.append((m.start(), m.end()))
    return hits


# ---------------------------------------------------------------- IBAN

# Country letters may be spelled one by one ("F I 2 1 ..."); digits may be spaced.
_IBAN_START = re.compile(r"(?<![A-Za-z0-9])([A-Za-z])[ \t]?([A-Za-z])[ \t]*(\d)[ \t]*(\d)")


def ibans(text):
    hits = []
    for m in _IBAN_START.finditer(text):
        cc = (m.group(1) + m.group(2)).upper()
        need = IBAN_LENGTHS.get(cc)
        if not need:
            continue
        chars = [cc, m.group(3), m.group(4)]
        n = 4
        pos = m.end()
        while n < need and pos < len(text):
            ch = text[pos]
            if ch.isascii() and ch.isalnum():
                chars.append(ch.upper())
                n += 1
            elif ch not in " \t":
                break
            pos += 1
        if n != need:
            continue
        if pos < len(text) and text[pos].isascii() and text[pos].isalnum():
            continue
        if iban_ok("".join(chars)):
            hits.append((m.start(), pos))
    return hits


# ---------------------------------------------------------------- EMAIL (email view)

_W = r"[A-Za-z0-9ÅÄÖåäö!#$%&'*+=?^_`{|}~]"
_WORD = rf"{_W}+(?:-{_W}+)*"
_SPELLED = r"(?:[A-Za-z0-9][ \t]+){2,}[A-Za-z0-9]"
_PART = rf"(?:{_SPELLED}|{_WORD})"
_LSEP = rf"(?:[ \t]*[._\-{SPOKEN_DOT}][ \t]*)"
_LOCAL = rf"{_PART}(?:{_LSEP}{_PART})*"
_AT = rf"[ \t]*[@{SPOKEN_AT}][ \t]*"
_SPELLED_LABEL = r"(?:[A-Za-z0-9][ \t]+)+[A-Za-z0-9]"  # domain labels may be 2 letters ("h s")
_DLAB = rf"(?:{_SPELLED_LABEL}|[A-Za-z0-9ÅÄÖåäö](?:[A-Za-z0-9ÅÄÖåäö-]*[A-Za-z0-9ÅÄÖåäö])?)"
_TLD = r"(?:(?:[A-Za-z][ \t]+)+[A-Za-z]|[A-Za-z]{2,24})"
_DSEP = rf"(?:\.|[ \t]*{SPOKEN_DOT}[ \t]*)"
_EMAIL_RE = re.compile(
    rf"(?<![A-Za-z0-9ÅÄÖåäö._-]){_LOCAL}{_AT}{_DLAB}(?:{_DSEP}{_DLAB})*{_DSEP}{_TLD}(?![A-Za-z0-9])"
)


def emails(text):
    if "@" not in text and SPOKEN_AT not in text:
        return []
    return [(m.start(), m.end()) for m in _EMAIL_RE.finditer(text)]


# ---------------------------------------------------------------- IP_ADDRESS

_IPV4_RE = re.compile(
    r"(?<![\d.])(\d{1,3})[ \t]*\.[ \t]*(\d{1,3})[ \t]*\.[ \t]*(\d{1,3})[ \t]*\.[ \t]*(\d{1,3})(?![\d]|\.\d)"
)
_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")


def ip_addresses(text):
    return _ips(text, identifying=True)


def private_ip_addresses(text):
    """Loopback, private-use, link-local, multicast: low severity (residual), never refused."""
    return _ips(text, identifying=False)


def _ips(text, identifying):
    hits = []
    for m in _IPV4_RE.finditer(text):
        try:
            ip = ipaddress.IPv4Address(".".join(str(int(g)) for g in m.groups()))
        except ValueError:
            continue
        if _ip_identifying(ip) is identifying:
            hits.append((m.start(), m.end()))
    for m in _IPV6_RE.finditer(text):
        if m.group(0).count(":") < 2:
            continue
        try:
            ip = ipaddress.IPv6Address(m.group(0))
        except ValueError:
            continue
        if _ip_identifying(ip) is identifying:
            hits.append((m.start(), m.end()))
    return hits


_NON_IDENTIFYING_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.168.0.0/16", "224.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "fe80::/10", "fc00::/7", "ff00::/8",
)]


def _ip_identifying(ip) -> bool:
    """Every address is a hit except loopback, unspecified, private-use, link-local, multicast.

    Documentation ranges (TEST-NET, 2001:db8::/32) are hits: they stand in for real addresses.
    """
    return not any(ip.version == n.version and ip in n for n in _NON_IDENTIFYING_NETS)


# ---------------------------------------------------------------- DEVICE_ID

_MAC_RE = re.compile(r"(?<![0-9A-Fa-f:-])[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:-])")
_IMEI_RE = re.compile(r"(?i)\bimei\b[^\d¦]{0,20}((?:\d[ \t-]?){14}\d)(?!\d)")
_BARE_15_RE = re.compile(r"(?<![\w-])\d{15}(?![\w-])")
_SERIAL_RE = re.compile(
    r"(?i)\b(?:serial\s*(?:number|no\.?)|s/n|sarjanumero\w*|serienummer\w*|device\s*id|laitetunnus\w*)"
    r"(?:[ \t]*(?:[:#=]|is|on|är))*[ \t]*([A-Za-z0-9][A-Za-z0-9-]{5,})"
)


def device_ids(text):
    hits = [(m.start(), m.end()) for m in _MAC_RE.finditer(text)]
    for m in _IMEI_RE.finditer(text):
        if luhn_ok(re.sub(r"\D", "", m.group(1))):
            hits.append(m.span())  # cue + value, so a value in the next turn touches the cue turn
    for m in _BARE_15_RE.finditer(text):
        if is_imei(m.group(0)) and not _overlaps_any(m.span(), hits):
            hits.append(m.span())
    for m in _SERIAL_RE.finditer(text):
        if any(ch.isdigit() for ch in m.group(1)):
            hits.append(m.span())
    return hits


# ---------------------------------------------------------------- LICENSE_PLATE

_PLATE_RE = re.compile(r"(?<![\w-])([A-ZÅÄÖ]{2,3})[ \t]*-[ \t]*([1-9]\d{0,2})(?![\w-]|\.\d)")
_PLATE_DENY = {
    "UTF", "ISO", "MP", "TV", "CS", "HTTP", "SHA", "MD", "AES", "RSA", "USB", "PS", "PC",
    "CD", "DVD", "ID", "NO", "OK", "EU", "EN", "KB", "MB", "GB", "TB", "IP", "AM", "PM",
    "VAT", "ALV", "CO", "PIN", "IT", "AI", "DSL", "LTE", "SIM", "NFC", "WPA", "GPS",
    "LED", "CPU", "FI", "SE", "HS", "MS", "XP", "IOS", "COV", "SAR", "WIN", "VER", "NR",
}


def plates(text):
    return [(m.start(), m.end()) for m in _PLATE_RE.finditer(text) if m.group(1) not in _PLATE_DENY]


# ---------------------------------------------------------------- SECRET
#
# One table for every secret-type cue (general-knowledge fi/sv/en). After the cue and up to
# four filler words, the value is collapsed from one token plus any following digit groups
# or single characters ("4 8 2 1", "k 4 x 9 q", "kissa 1 2 3"); spoken digits arrive already
# converted by the digit view. The hit spans cue + value, so a value in the next turn is
# caught by the N-turn windows. Kinds:
#   digits   - collapsed value all digits, length lo..hi
#   code     - alphanumeric, contains a digit, length lo..hi
#   secret   - length >= lo and secret-like (digit, inner capital or symbol), or >= 4 spelled chars

_CUE_TABLE = [
    ("digits", 3, 4,
     (r"cvv2?|cvc2?|cvn|card\s+verification\s+(?:code|value)|turvakoodi\w*|turvanumero\w*|"
     r"säkerhetskod\w*|security\s+code")),
    ("digits", 4, 8,
     (r"pin(?:[ -]?(?:koodi\w*|kod\w*|code|number|numero\w*|nummer\w*))?|pinkod\w*|"
     r"tunnuslu(?:ku|vu)\w*|personal\s+identification\s+number")),
    ("code", 4, 10,
     (r"otp|one[\s-]?time\s+(?:code|password|passcode|pin)|verification\s+code|"
     r"confirmation\s+code|auth(?:entication)?\s+code|sms\s+code|login\s+code|access\s+code|"
     r"vahvistuskoodi\w*|varmennuskoodi\w*|kertakäyttö(?:koodi|salasana)\w*|"
     r"tekstiviestikoodi\w*|engångs(?:kod|lösenord)\w*|verifieringskod\w*|bekräftelsekod\w*")),
    ("secret", 4, 128,
     (r"password|passwd|pwd|passcode|passphrase|salasana\w*|tunnussana\w*|lösenord\w*|"
     r"api[ _-]?(?:key|avain\w*|nyckel\w*)|token|secret\s+key")),
]
_CUES = [(kind, lo, hi, re.compile(r"(?i)\b(?<!-)(?:" + rx + r")(?![\w])")) for kind, lo, hi, rx in _CUE_TABLE]
_FILLERS = {
    "is", "was", "on", "oli", "är", "var", "it's", "its", "my", "minun", "min", "mitt", "the",
    "your", "now", "nyt", "nu", "code", "koodi", "kod", "number", "numero", "nummer", ":", "=",
    "#", "-",
}
_VTOK = re.compile(r"[ \t]*([^\s\u00a6,;]+)")
_TRAIL = ".!?)\"'"
_SECRET_PATTERNS = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}|"
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"
)


def _secret_like(tok: str) -> bool:
    has_digit = any(c.isdigit() for c in tok)
    mixed = any(c.isupper() for c in tok[1:]) and any(c.islower() for c in tok)
    symbol = any(not c.isalnum() for c in tok)
    return has_digit or mixed or symbol


def _cue_value(text, pos):
    """(collapsed value, end offset, token count, all single chars) after a cue, or None."""
    fillers = 0
    while True:
        m = _VTOK.match(text, pos)
        if not m:
            return None
        tok = m.group(1).rstrip(_TRAIL).lstrip(":=#")
        if (not tok or tok.lower() in _FILLERS) and fillers < 4:
            pos, fillers = m.end(), fillers + 1
            continue
        break
    if not tok:
        return None
    parts = [tok]
    end = m.start(1) + len(m.group(1).rstrip(_TRAIL))
    pos = m.end()
    while True:
        n = _VTOK.match(text, pos)
        if not n:
            break
        t = n.group(1).rstrip(_TRAIL)
        if not t or not (t.isdigit() or (len(t) == 1 and t.isalnum())):
            break
        parts.append(t)
        end = n.start(1) + len(t)
        pos = n.end()
        if n.group(1) != t:  # trailing punctuation ends the value
            break
    single = len(parts) >= 2 and all(len(x) == 1 for x in parts)
    return "".join(parts), end, single


def _value_ok(kind, lo, hi, value, single):
    if kind == "digits":
        digits = value.replace("-", "")
        return digits.isdigit() and lo <= len(digits) <= hi
    if kind == "code":
        return value.isalnum() and any(c.isdigit() for c in value) and lo <= len(value) <= hi
    return len(value) >= lo and len(value) <= hi and (_secret_like(value) or single)


def secrets(text):
    hits = [(m.start(), m.end()) for m in _SECRET_PATTERNS.finditer(text)]
    urls = [m.span() for m in _URL_RE.finditer(text)]
    for kind, lo, hi, cue in _CUES:
        for m in cue.finditer(text):
            if _overlaps_any(m.span(), urls):
                continue
            got = _cue_value(text, m.end())
            if got is None:
                continue
            value, end, single = got
            if _value_ok(kind, lo, hi, value, single):
                hits.append((m.start(), end))  # cue + value: a next-turn value touches the cue turn
    return hits


# ---------------------------------------------------------------- URL with tokens

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s¦<>\"']+")
_TOKEN_KEYS = {
    "token", "access_token", "auth", "authtoken", "key", "apikey", "api_key", "sig",
    "signature", "session", "sessionid", "sid", "code", "password", "pwd", "reset",
    "otp", "secret", "jwt", "id_token", "refresh_token",
}
_RANDOM_SEG = re.compile(r"[A-Za-z0-9_-]{24,}")


def urls_with_tokens(text):
    hits = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,!?)")
        try:
            parts = urlsplit(url if "://" in url else "http://" + url)
        except ValueError:
            hits.append(m.span())
            continue
        keys = {k.lower() for k, _ in parse_qsl(parts.query, keep_blank_values=True)}
        seg_hit = any(
            _RANDOM_SEG.fullmatch(seg) and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg)
            for seg in parts.path.split("/")
        )
        if keys & _TOKEN_KEYS or seg_hit:
            hits.append((m.start(), m.start() + len(url)))
    return hits


# ---------------------------------------------------------------- USERNAME

_USER_CUE = re.compile(
    r"(?i)\b(?:username|user\s*name|user\s*id|login|käyttäjätunnu\w*|käyttäjänim\w*|"
    r"användarnamn\w*|användar-id)\b(?:[ \t]*(?:[:=]|is|was|on|oli|är|var))*[ \t]*([A-Za-z0-9._-]{3,})"
)
_HANDLE_RE = re.compile(r"(?<![\w.@])@[A-Za-z][A-Za-z0-9_.]{2,29}")
_USER_STOP = {"the", "same", "your", "my", "not", "and", "that", "this", "is", "was", "please",
              "page", "screen", "details", "info", "problem", "issue", "doesn", "didn", "isn"}


def usernames(text):
    hits = [(m.start(), m.end()) for m in _HANDLE_RE.finditer(text)]
    for m in _USER_CUE.finditer(text):
        if m.group(1).lower().strip("._-") not in _USER_STOP:
            hits.append(m.span())
    return hits


# ---------------------------------------------------------------- ACCOUNT_NUMBER

_ACCOUNT_CUE = re.compile(
    r"(?i)\b(?:account\s*(?:number|no\.?|nr\.?|#)|acct\.?|tilinumero\w*|asiakasnumero\w*|"
    r"customer\s*(?:number|no\.?|nr\.?|id)|kontonummer\w*|kundnummer\w*|"
    r"member(?:ship)?\s*(?:number|no\.?)|jäsennumero\w*|contract\s*number|sopimusnumero\w*|"
    r"avtalsnummer\w*|policy\s*number|vakuutusnumero\w*)"
    r"(?:[ \t]*(?:[:#=]|is|was|on|oli|är|var))*[ \t]*((?:[A-Za-z]{1,4}[ \t-]?)?\d(?:[ \t-]?\d){4,})"
)


def account_numbers(text):
    iban_spans = ibans(text)
    # cue + value span, so a value in the turn after its cue touches the cue turn
    return [m.span() for m in _ACCOUNT_CUE.finditer(text) if not _overlaps_any(m.span(1), iban_spans)]


# ---------------------------------------------------------------- PROPERTY_ID

_PROPERTY_RE = re.compile(
    r"(?<![\d-])\d{1,3}[ \t]*-[ \t]*\d{1,3}[ \t]*-[ \t]*\d{1,4}[ \t]*-[ \t]*\d{1,4}(?![\d-])"
)


def property_ids(text):
    return [(m.start(), m.end()) for m in _PROPERTY_RE.finditer(text)]


# ---------------------------------------------------------------- registry of labels

# assertion name -> (label, detector, view)
LABELS = {
    "nationalIds": ("NATIONAL_ID", national_ids, "digit"),
    "paymentCards": ("PAYMENT_CARD", payment_cards, "digit"),
    "ibans": ("IBAN", ibans, "digit"),
    "accountNumbers": ("ACCOUNT_NUMBER", account_numbers, "digit"),
    "emails": ("EMAIL", emails, "email"),
    "phones": ("PHONE", phones, "digit"),
    "ipAddresses": ("IP_ADDRESS", ip_addresses, "digit"),
    "deviceIds": ("DEVICE_ID", device_ids, "digit"),
    "usernames": ("USERNAME", usernames, "digit"),
    "propertyIds": ("PROPERTY_ID", property_ids, "digit"),
    "plates": ("LICENSE_PLATE", plates, "digit"),
    "secrets": ("SECRET", secrets, "digit"),
    "urlsWithTokens": ("URL", urls_with_tokens, "digit"),
}
