"""Independent identifier validators for the gate (no shared code with detector or redactor).

Each finder takes one cell string and returns (high, low): how many matches of each severity.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

_NB = r"(?<![0-9A-Za-z])"  # no alnum before
_NA = r"(?![0-9A-Za-z])"  # no alnum after


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def luhn(d: str) -> bool:
    tot = 0
    for i, ch in enumerate(reversed(d)):
        n = ord(ch) - 48
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        tot += n
    return tot % 10 == 0


# --- national IDs (Finnish HETU with checksum) ---------------------------------------------
_HETU = re.compile(_NB + r"(\d{2})(\d{2})(\d{2})([-+A-FYXWVU])(\d{3})([0-9A-Y])" + _NA, re.IGNORECASE)
_HETU_CHK = "0123456789ABCDEFHJKLMNPRSTUVWXY"


def national_ids(s):
    n = 0
    for m in _HETU.finditer(s):
        dd, mm, yy, _, nnn, chk = m.groups()
        if 1 <= int(dd) <= 31 and 1 <= int(mm) <= 12 and _HETU_CHK[int(dd + mm + yy + nnn) % 31] == chk.upper():
            n += 1
    return n, 0


# --- payment cards (Luhn + issuer prefix) ---------------------------------------------------
_CARD = re.compile(_NB + r"(\d(?:[ -]?\d){12,18})" + _NA)


def _card_ok(d: str) -> bool:
    if not (13 <= len(d) <= 19) or not luhn(d):
        return False
    if len(d) == 15:
        return d[:2] in ("34", "37")
    return d[0] in "456" or d[:2] == "35" or "22" <= d[:2] <= "27" or (d[0] == "3" and d[:2] in ("30", "36", "38", "39"))


def payment_cards(s):
    return sum(1 for m in _CARD.finditer(s) if _card_ok(_digits(m.group(1)))), 0


# --- IBAN (mod-97, country length) -----------------------------------------------------------
# Case-insensitive; groups may be separated by up to two spaces/dashes. Validated after normalising.
_IBAN = re.compile(_NB + r"([A-Z]{2}\d{2}(?:[\s-]{0,2}[A-Z0-9]){11,30})" + _NA, re.IGNORECASE)
_IBAN_SEP = re.compile(r"[\s-]+")
# ISO 13616 registry lengths (European/SEPA subset). Countries not listed: any length 15..34 with valid mod-97.
_IBAN_LEN = {"AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "EE": 20,
             "ES": 24, "FI": 18, "FO": 18, "FR": 27, "GB": 22, "GI": 23, "GL": 18, "GR": 27, "HR": 21, "HU": 28,
             "IE": 22, "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18,
             "NO": 15, "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27}


def _iban_ok(raw: str) -> bool:
    s = _IBAN_SEP.sub("", raw)
    want = _IBAN_LEN.get(s[:2].upper())
    if want is None and not s.isupper():
        return False  # unlisted country: only upper-case text (limits mod-97 chance hits on lower-case words)
    s = s.upper()
    if (want is not None and len(s) != want) or not (15 <= len(s) <= 34):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(ch, 36)) for ch in r)) % 97 == 1


def ibans(s):
    n = 0
    for m in _IBAN.finditer(s):
        raw = m.group(1)
        glued = (m.start() > 0 and s[m.start() - 1] in "_-") or (m.end() < len(s) and s[m.end()] in "_-")
        if glued and not _IBAN_SEP.sub("", raw)[:2].isupper():
            continue  # lower/mixed case joined to an identifier by _ or -: pseudonym text, not an IBAN
        # try the longest prefix that validates (trailing words may be swallowed by the pattern)
        parts = _IBAN_SEP.split(raw)
        for k in range(len(parts), 0, -1):
            if _iban_ok("".join(parts[:k])):
                n += 1
                break
    return n, 0


# --- account / customer / contract / invoice / order numbers (cue + number) ------------------
_ACCT = re.compile(
    r"(?i)\b(?:asiakas(?:numero|nro)|sopimus(?:numero|nro)|lasku(?:n)?\s?(?:numero|nro)|tilaus(?:numero|nro)|"
    r"tili(?:numero|nro)|kundnummer|kundnr|avtalsnummer|fakturanummer|ordernummer|kontonummer|"
    r"(?:customer|account|contract|invoice|order|reference)\s?(?:number|no\.?|nr|id|#))"
    r"\W{0,6}(?:on|is|är|:)?\W{0,4}(\d[\d -]{4,18}\d)" + _NA)


def account_numbers(s):
    return len(_ACCT.findall(s)), 0


# --- emails ----------------------------------------------------------------------------------
_EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")


def emails(s):
    return len(_EMAIL.findall(s)), 0


# --- phones (international with +/00, Finnish mobile, Finnish landline with separators) -------
_PHONE = re.compile(
    r"(?<![\w+])(?:(?:\+|00)[1-9]\d{0,2}[\s-]?(?:\(0\)[\s-]?)?(?:\d[\s-]?){5,12}\d"
    r"|0(?:4\d|50)(?:[\s-]?\d){5,8}"
    r"|0[1-9]\d?[\s-]\d{3,4}[\s-]?\d{2,4})(?![\w.,]\d|\w)")


def phones(s):
    n = 0
    hetu_spans = [m.span() for m in _HETU.finditer(s) if national_ids(m.group(0))[0]]
    for m in _PHONE.finditer(s):
        if any(a <= m.start() < b for a, b in hetu_spans):
            continue  # a valid HETU is counted by nationalIds, not as a phone
        if 7 <= len(_digits(m.group(0))) <= 15:
            n += 1
    return n, 0


# --- IP addresses ------------------------------------------------------------------------------
_IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w]|\.\d)")
_IPV6 = re.compile(r"(?<![\w:])((?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4})(?![\w:])")


def _ip_sev(ip) -> str:
    return "low" if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified
                     or ip.is_reserved or ip.is_multicast) else "high"


def ip_addresses(s):
    hi = lo = 0
    for rx in (_IPV4, _IPV6):
        for m in rx.finditer(s):
            cand = m.group(1)
            if rx is _IPV6 and cand.count(":") < 7 and "::" not in cand:
                continue
            try:
                ip = ipaddress.ip_address(cand)
            except ValueError:
                continue
            if _ip_sev(ip) == "high":
                hi += 1
            else:
                lo += 1
    return hi, lo


# --- device IDs (IMEI 15 Luhn, ICCID 89..., MAC) ----------------------------------------------
_IMEI = re.compile(_NB + r"(\d{15})" + _NA)
_ICCID = re.compile(_NB + r"(89\d{17,18})" + _NA)
_MAC = re.compile(r"(?<![0-9A-Fa-f:-])[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}(?![0-9A-Fa-f:-])"
                  r"|(?<![0-9A-Fa-f.])[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}(?![0-9A-Fa-f.])")


def device_ids(s):
    n = sum(1 for m in _IMEI.finditer(s) if luhn(m.group(1)))
    n += sum(1 for m in _ICCID.finditer(s) if luhn(m.group(1)))
    n += sum(1 for _ in _MAC.finditer(s))
    return n, 0


# --- cue + value rule shared by usernames and secrets ------------------------------------------
# Same shape as the redactor (ticket 12): a value counts after a cue + copula/colon ("is", "on", "är", ":",
# optional hedge) unless it is a function/prose word; without a copula only a credential-shaped token counts.
_HEDGE = (r"(?:varmaan|kai|luultavasti|ehkä|probably|maybe|still|edelleen|nog|kanske|typ|fortfarande|nyt|now|nu)")
_COPULA_VALUE = (
    r"(?P<sep>[^\w\[]{0,4}(?:(?:on|oli|is|was|är|var)\b|[:=]))?[^\w\[]{0,4}"
    r"(?:" + _HEDGE + r"\b[^\w\[]{1,3})?"
    r"(?P<val>[^\s\[\]\"',;]{3,64})")
_PROSE = frozenset("""
varmaan kai luultavasti ehkä probably maybe nog kanske typ fortfarande nyt now nu
the and for with that this those these your you our their his her its not none never wrong incorrect invalid
expired changed correct right okay fine working broken locked blocked lost forgotten unknown new old same different
too very still also just really should would could will can cannot must may might was were been being are has have
had does did doesn didn isn aren wasn not reset link page screen details info information problem issue account
service router modem network login logout user name username code number what which when where why how who from
into onto over under about after before again because while until once only even such some any all each every both
other another more most much many few less least own than then there here yes ok sure please thanks thank
ei eikä oikea väärä vanha uusi sama eri liian tosi vielä myös vain hukassa lukossa voimassa vanhentunut vaihdettu
unohtunut kadonnut estetty jotain mikä mitä tämä tuo sinun teidän minun hyvä huono ja tai mutta koska kun jos kaikille kaikki
kaikissa kaikkiin palveluille palveluun tunnus tunnukset lukittu lukittuna toimi toimii sivu sivulla ongelma
inte icke fel rätt gammal gamla ny nya samma annan fär mycket också bara glömt ändrat borta läst spärrat något vad
detta det din ditt er bra dålig och eller men för
""".split())


def _credential_shaped(v: str) -> bool:
    core = v.rstrip(".!?)")
    if not core:
        return False
    has_l = any(c.isalpha() for c in core)
    has_d = any(c.isdigit() for c in core)
    inner_sym = any(c in "!#$%&*+=?@_~^/\\" for c in core)
    mixed = any(c.isupper() for c in core[1:]) and any(c.islower() for c in core)
    return has_d or (inner_sym and has_l) or mixed or (len(core) >= 20 and core.isalnum())


def _cued_value_counts(m, *, alpha_without_copula: bool) -> bool:
    v = m.group("val")
    if _credential_shaped(v):
        return True
    core = v.rstrip(".!?)")
    if core.lower() in _PROSE or not core.isalpha() or len(core) < 3:
        return False
    return m.group("sep") is not None or alpha_without_copula


# --- usernames (cue + handle, or @handle not part of an email) ---------------------------------
_USER = re.compile(
    r"(?i)\b(?:käyttäjätunnu(?:s|ksella|ksen|kseni)|käyttäjänimi|tunnukse(?:ni|lla|en)|username|user\s?name|"
    r"login|user\s?id|användarnamn|användar-?id)"
    + _COPULA_VALUE)
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_]{3,30})(?![\w@.]*\.[A-Za-z]{2,})")


def usernames(s):
    # the cue is required; after a copula/colon a purely alphabetic value counts, without one only a
    # credential-shaped or non-prose value does (the shape the redactor uses)
    n = sum(1 for m in _USER.finditer(s) if _cued_value_counts(m, alpha_without_copula=True))
    n += len(_HANDLE.findall(s))
    return n, 0


# --- Finnish property IDs (kiinteistötunnus) ---------------------------------------------------
_PROP = re.compile(r"(?<![\w-])\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}(?![\w-])")


def property_ids(s):
    return len(_PROP.findall(s)), 0


# --- licence plates (Finnish ABC-123) -----------------------------------------------------------
_PLATE = re.compile(r"(?<![\w-])[A-ZÅÄÖ]{2,3}-\d{1,3}(?![\w-])", re.IGNORECASE)


def plates(s):
    return len(_PLATE.findall(s)), 0


# --- secrets (known key shapes; cue + value with a digit) --------------------------------------
_KEYSHAPES = re.compile(
    r"AKIA[0-9A-Z]{16}|\bsk_(?:live|test)_[0-9A-Za-z]{10,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}")
_SECRET_CUE = re.compile(
    r"(?i)\b(?:salasana(?:ni|na)?|password|passwd|pwd|lösenord(?:et)?|pin(?:-?koodi|-?kod|\s?code)?|puk(?:-?koodi|-?kod)?|"
    r"wi-?fi(?:-?avain|-?salasana|\s?key|\s?password)?|wlan(?:-?avain)?|wpa\d?)"
    + _COPULA_VALUE)


def secrets(s):
    n = len(_KEYSHAPES.findall(s))
    # cue + (copula|colon) + value, or cue + a credential-shaped token (digit, symbol, mixed case, long);
    # cued everyday words ("password for the router", "password reset") are not values
    n += sum(1 for m in _SECRET_CUE.finditer(s) if _cued_value_counts(m, alpha_without_copula=False))
    return n, 0


# --- URLs carrying tokens ---------------------------------------------------------------------
_URL = re.compile(r"(?i)\bhttps?://[^\s<>\"'\]]+")
_TOKEN_KEYS = {"token", "access_token", "auth", "key", "apikey", "api_key", "sig", "signature", "session", "sid",
               "code", "otp", "reset", "password", "pwd", "email", "user", "uid", "jwt", "secret"}
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def _url_has_token(u: str) -> bool:
    try:
        parts = urlsplit(u.rstrip(".,;:)"))
    except ValueError:
        return True  # unparseable URL: treat as suspicious
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if k.lower() in _TOKEN_KEYS or "@" in v or (_OPAQUE.match(v) and any(c.isdigit() for c in v)):
            return True
    if parts.username or parts.password:
        return True
    for seg in parts.path.split("/"):
        if _OPAQUE.match(seg) and any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg):
            return True
    return bool(parts.fragment and ("token" in parts.fragment.lower() or "@" in parts.fragment))


def urls_with_tokens(s):
    return sum(1 for m in _URL.finditer(s) if _url_has_token(m.group(0))), 0


# --- raw timestamps (minute or second precision) ------------------------------------------------
# Every supported format captures (hour, minute, second?, fraction?); any non-zero sub-hour part is a hit.
_ISO_TS = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?(?!\d)")
_FI_TS = re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}\.\d{4}\s*(?:klo|kl\.?|at|,)?\s*"
                    r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2})(?:[.,](\d+))?)?(?!\d)")
TIMESTAMP_FORMATS = (_ISO_TS, _FI_TS)


def _sub_hour(m) -> bool:
    _, minute, second, frac = m.groups()
    return minute != "00" or (second or "00") != "00" or bool((frac or "").strip("0"))


def raw_timestamps(s):
    return sum(1 for rx in TIMESTAMP_FORMATS for m in rx.finditer(s) if _sub_hour(m)), 0


# --- 64-hex anywhere --------------------------------------------------------------------------
HEX64_ANY = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
HEX64_TOKEN = re.compile(r"[0-9a-f]{64}")


def hex64(s):
    return len(HEX64_ANY.findall(s)), 0
