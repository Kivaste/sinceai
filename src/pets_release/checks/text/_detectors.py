"""Gate-side identifier detectors over normalised text. Independent of the redactor.

Each detector takes one string (a normalised view of a turn or of a joined window) and
returns a list of (start, end) character spans. Validators are checksum- or structure-based
where the label has one (HETU, Luhn, IBAN mod-97, IP parsing).
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

import pets_release.checks._cues as _cues

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

# separators between digit groups: spaces/tabs, one dash, and one comma or line break (#56: spoken phones)
_PHONE_RE = re.compile(
    r"(?<![\w+.,/])(\+[ \t]*)?\(?\d+\)?(?:[ \t]*(?:[,\n][ \t\n]*)?-?[ \t]*\(?\d+\)?)*(?![\w/])"
)
_DATE_LIKE = re.compile(r"^\d{1,2}[-./ ]\d{1,2}[-./ ]\d{2,4}$")


def _overlaps_any(span, spans):
    return any(s < span[1] and span[0] < e for s, e in spans)


def _phone_ok(raw: str, plus: bool) -> bool:
    digits = re.sub(r"\D", "", raw)
    if _DATE_LIKE.match(raw.strip()):
        return False
    if plus:
        return 8 <= len(digits) <= 15
    if digits.startswith("00"):
        return 10 <= len(digits) <= 15
    return bool(re.fullmatch(r"0[1-9]\d{5,9}", digits))


_PHONE_WORD = re.compile(r"[^ \t]+")


def _split_run(text, start, end):
    """Greedy left-to-right split of an over-long digit run into phone numbers at spaces.

    Used only when the whole run is not one valid number (two numbers written side by side).
    """
    words = [(m.start() + start, m.end() + start) for m in _PHONE_WORD.finditer(text[start:end])]
    out = []
    i = 0
    while i < len(words):
        found = None
        for j in range(len(words), i, -1):
            a, b = words[i][0], words[j - 1][1]
            raw = text[a:b]
            if _phone_ok(raw, raw.lstrip().startswith("+")) and not (i == 0 and j == len(words)):
                found = (a, b, j)
                break
        if found:
            out.append((found[0], found[1]))
            i = found[2]
        else:
            i += 1
    return out


def phones(text):
    hits = []
    hetus = national_ids(text)
    for m in _PHONE_RE.finditer(text):
        if _overlaps_any(m.span(), hetus):
            continue
        raw = m.group(0)
        if _phone_ok(raw, bool(m.group(1))):
            hits.append((m.start(), m.end()))
        elif not _DATE_LIKE.match(raw.strip()):
            hits.extend(_split_run(text, m.start(), m.end()))
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

_PLATE_RE = re.compile(r"(?i)(?<![\w-])([A-ZÅÄÖ]{2,3})[ \t]*-[ \t]*([1-9]\d{0,2})(?![\w-]|\.\d)")
_PLATE_DENY = {
    "UTF", "ISO", "MP", "TV", "CS", "HTTP", "SHA", "MD", "AES", "RSA", "USB", "PS", "PC",
    "CD", "DVD", "ID", "NO", "OK", "EU", "EN", "KB", "MB", "GB", "TB", "IP", "AM", "PM",
    "VAT", "ALV", "CO", "PIN", "IT", "AI", "DSL", "LTE", "SIM", "NFC", "WPA", "GPS",
    "LED", "CPU", "FI", "SE", "HS", "MS", "XP", "IOS", "COV", "SAR", "WIN", "VER", "NR",
}


def plates(text):
    return [(m.start(), m.end()) for m in _PLATE_RE.finditer(text) if m.group(1).upper() not in _PLATE_DENY]


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
_SKIP_WORDS = _FILLERS | _cues.FUNCTION_WORDS
# The digit view masks exact redactor placeholders as "\u00a6" (``_normalise.MASK``): one token here.
_MASKED = "\u00a6"
_VTOK = re.compile(r"[ \t]*(\u00a6|[,;]|[^\s\u00a6,;]+)")
_SENTENCE_END = ".!?;"
_TRAIL = ".)\"'"  # "!" and "?" stay on the value: they can be password symbols
_TAIL_PUNCT = "!?"
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


def _collapse(text, m):
    """(collapsed value, end offset, all single chars) from the value token ``m`` plus any following
    digit groups or single characters."""
    tok = m.group(1).rstrip(_TRAIL).lstrip(":=#")
    parts = [tok]
    end = m.start(1) + len(m.group(1).rstrip(_TRAIL))
    pos = m.end()
    while True:
        n = _VTOK.match(text, pos)
        if not n:
            break
        t = n.group(1).rstrip(_TRAIL)
        core = t.rstrip(_TAIL_PUNCT)
        if not core or not (core.isdigit() or (len(core) == 1 and core.isalnum())):
            break
        parts.append(t)
        end = n.start(1) + len(t)
        pos = n.end()
        if n.group(1) != core:  # trailing punctuation ends the value
            break
    single = len(parts) >= 2 and all(len(x) == 1 for x in parts)
    return "".join(parts), end, single


# the cue scan crosses line breaks (as the cell rescan does); value collapsing does not
_CTOK = re.compile(r"\s*(" + _MASKED + r"|[,;]|[^\s" + _MASKED + r",;]+)")


def _cue_end(kind, lo, hi, text, pos):
    """End offset of the value after a cue ending at ``pos``, or None. Same rule as the cell rescans
    (``cells._validators._cued_value_counts``), over up to ``_cues.WINDOW`` tokens, never past a
    sentence end: a value-shaped token counts anywhere; a copula (also a trailing ":") arms, and while
    armed the first word that is not a hedge is the value unless it is prose; any later copula re-arms;
    other function words and non-value words disarm; separator runs are skipped; a masked placeholder
    is the redacted value (skipped, disarms) unless a value is glued to it."""
    armed = False
    words = 0
    for _ in range(_cues.WINDOW):
        m = _CTOK.match(text, pos)
        if not m:
            return None
        pos = m.end()
        raw = m.group(1)
        if raw == _MASKED or _cues.is_placeholder(raw.rstrip(_TRAIL)):
            # ``_normalise.MASK`` is " <mask> ": exactly one space and then a value character means the
            # source glued a value to the placeholder ("[SECRET_1]hunterxyz")
            glued = raw == _MASKED and text[pos:pos + 1] == " " and text[pos + 1:pos + 2].isalnum()
            if not glued:
                armed = False
            continue
        if raw[:1] in ":=":
            armed = True
        tok = raw.rstrip(_TRAIL).lstrip(":=#")
        last = raw.rstrip("\"')]")[-1:]
        ends = bool(last) and last in _SENTENCE_END
        low = tok.rstrip(_TAIL_PUNCT + ":=").lower()
        arms_after = tok.rstrip(_TAIL_PUNCT)[-1:] in (":", "=") and not ends  # "router: x"
        if _cues.is_punct(low):
            if ends:
                return None
            armed = armed or arms_after
            continue
        first_word = words == 0
        words += 1
        if low in _cues.COPULAS:
            armed = True
            continue
        if low in _cues.HEDGES:
            if ends:
                return None
            continue
        if low in _SKIP_WORDS:
            armed = arms_after  # "is a pain", "is not working": a description, not a value
            if ends:
                return None
            continue
        value, end, single = _collapse(text, m)
        nxt = _CTOK.match(text, end)
        nxt = nxt.group(1) if nxt else ""
        # a plain word directly before a placeholder is not the value: the placeholder is
        before_ph = nxt == _MASKED or _cues.is_placeholder(nxt.rstrip(_TRAIL))
        plain = (armed or (kind == "username" and first_word)) and not before_ph
        if _value_ok(kind, lo, hi, value, single, armed, plain):
            return end
        pos = max(pos, end)  # a rejected collapsed value ("4321 0000 0000 99") is not re-read in parts
        if ends:
            return None
        armed = arms_after  # not the value; a later copula re-arms
    return None


_USERNAME_VALUE = re.compile(r"[A-Za-z0-9._@-]+")


def _value_ok(kind, lo, hi, value, single, copula=True, plain=None):
    """``copula``: armed by a copula; ``plain``: a plain word may be the value (default: ``copula``)."""
    plain = copula if plain is None else plain
    if kind == "username":
        v = value.strip("[]()<>\"'").rstrip(_TAIL_PUNCT + ":")
        if not (lo <= len(v) <= hi and _USERNAME_VALUE.fullmatch(v)):
            return False
        if _secret_like(v.strip("._-")):  # digit, inner symbol or mixed case: a handle
            return True
        return plain and v.lower().strip("._-") not in _cues.PROSE_WORDS | _USER_STOP
    if kind != "secret":
        value = value.rstrip(_TAIL_PUNCT)
    if kind == "digits":
        digits = value.replace("-", "")
        return digits.isdigit() and lo <= len(digits) <= hi
    if kind == "code":
        return value.isalnum() and any(c.isdigit() for c in value) and lo <= len(value) <= hi
    value = value.rstrip(":")  # "label:" after a cue is prose, not a symbol
    if not copula:  # no copula/colon: only a credential-shaped token counts ("password reset?" is prose)
        value = value.rstrip(_TAIL_PUNCT)
    if not lo <= len(value) <= hi:
        return False
    if _cues.DATE_OR_TIME.fullmatch(value.rstrip(_TAIL_PUNCT)):
        return plain  # a date counts only right after a copula, as in the cell rescan
    if _secret_like(value) or single:
        return True
    # cue + copula/colon + a word that is not everyday prose ("salasana on kissakala")
    word = value.rstrip(_TAIL_PUNCT).lower()
    return plain and any(c.isalpha() for c in word) and word not in _cues.PROSE_WORDS


def secrets(text):
    hits = [(m.start(), m.end()) for m in _SECRET_PATTERNS.finditer(text)]
    urls = [m.span() for m in _URL_RE.finditer(text)]
    for kind, lo, hi, cue in _CUES:
        for m in cue.finditer(text):
            if _overlaps_any(m.span(), urls):
                continue
            end = _cue_end(kind, lo, hi, text, m.end())
            if end is not None:
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
        # the fragment too (#56): "#token=...", "#/cb?code=...", "#/reset/<token>"
        frag_path, _, frag_query = parts.fragment.partition("?")
        for q in (frag_query, frag_path if "=" in frag_path else ""):
            keys |= {k.lower().lstrip("/") for k, _ in parse_qsl(q, keep_blank_values=True)}
        seg_hit = any(
            _RANDOM_SEG.fullmatch(seg) and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg)
            for seg in parts.path.split("/") + re.split(r"[/=&]", parts.fragment)
        )
        if keys & _TOKEN_KEYS or seg_hit:
            hits.append((m.start(), m.start() + len(url)))
    return hits


# ---------------------------------------------------------------- USERNAME

_USER_CUE = re.compile(
    r"(?i)\b(?:username|user\s*name|user\s*id|login|käyttäjätunnu\w*|käyttäjänim\w*|"
    r"användarnamn\w*|användar-id)\b"
)
_HANDLE_RE = re.compile(r"(?<![\w.@])@[A-Za-z][A-Za-z0-9_.]{2,29}")
_USER_STOP = {"the", "same", "your", "my", "not", "and", "that", "this", "is", "was", "please",
              "page", "screen", "details", "info", "problem", "issue", "doesn", "didn", "isn"}


def usernames(text):
    hits = [(m.start(), m.end()) for m in _HANDLE_RE.finditer(text)]
    for m in _USER_CUE.finditer(text):
        # the shared cue rule (``_cue_end``): a handle-shaped token anywhere in the clause, or a plain
        # word right after the cue or after a copula, unless it is prose
        end = _cue_end("username", 3, 64, text, m.end())
        if end is not None:
            hits.append((m.start(), end))
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
