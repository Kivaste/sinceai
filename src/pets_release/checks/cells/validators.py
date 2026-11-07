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
_IBAN = re.compile(_NB + r"([A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30})" + _NA)
_IBAN_LEN = {"FI": 18, "SE": 24, "NO": 15, "DK": 18, "DE": 22, "EE": 20, "GB": 22, "FR": 27, "NL": 18, "ES": 24,
             "IT": 27, "BE": 16, "AT": 20, "CH": 21, "PL": 28, "LT": 20, "LV": 21, "IE": 22, "PT": 29, "IS": 26}


def _iban_ok(raw: str) -> bool:
    s = raw.replace(" ", "")
    want = _IBAN_LEN.get(s[:2])
    if (want is not None and len(s) != want) or not (15 <= len(s) <= 34):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(ch, 36)) for ch in r)) % 97 == 1


def ibans(s):
    n = 0
    for m in _IBAN.finditer(s):
        raw = m.group(1)
        # try the longest prefix that validates (trailing words may be swallowed by the pattern)
        parts = raw.split(" ")
        for k in range(len(parts), 0, -1):
            if _iban_ok(" ".join(parts[:k])):
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


# --- usernames (cue + handle, or @handle not part of an email) ---------------------------------
_USER = re.compile(
    r"(?i)\b(?:käyttäjätunnu(?:s|ksella|ksen|kseni)|käyttäjänimi|tunnukse(?:ni|lla|en)|username|user\s?name|"
    r"login|user\s?id|användarnamn|användar-?id)\W{0,4}(?:on|is|är|:|=)?\W{0,4}([A-Za-z0-9][A-Za-z0-9._-]{2,31})")
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_]{3,30})(?![\w@.]*\.[A-Za-z]{2,})")


def usernames(s):
    n = sum(1 for m in _USER.finditer(s) if any(ch.isdigit() or ch in "._" for ch in m.group(1)))
    n += len(_HANDLE.findall(s))
    return n, 0


# --- Finnish property IDs (kiinteistötunnus) ---------------------------------------------------
_PROP = re.compile(r"(?<![\w-])\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}(?![\w-])")


def property_ids(s):
    return len(_PROP.findall(s)), 0


# --- licence plates (Finnish ABC-123) -----------------------------------------------------------
_PLATE = re.compile(r"(?<![\w-])[A-ZÅÄÖ]{2,3}-\d{1,3}(?![\w-])")


def plates(s):
    return len(_PLATE.findall(s)), 0


# --- secrets (known key shapes; cue + value with a digit) --------------------------------------
_KEYSHAPES = re.compile(
    r"AKIA[0-9A-Z]{16}|\bsk_(?:live|test)_[0-9A-Za-z]{10,}|\bgh[pousr]_[A-Za-z0-9]{30,}|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}")
_SECRET_CUE = re.compile(
    r"(?i)\b(?:salasana(?:ni|na)?|password|passwd|pwd|lösenord(?:et)?|pin(?:-?koodi|-?kod|\s?code)?|puk(?:-?koodi|-?kod)?|"
    r"wi-?fi(?:-?avain|-?salasana|\s?key|\s?password)?|wlan(?:-?avain)?|wpa\d?)"
    r"\W{0,4}(?:on|is|är|:|=)?\W{0,4}([^\s\[\]\"',;]{3,64})")


def secrets(s):
    n = len(_KEYSHAPES.findall(s))
    n += sum(1 for m in _SECRET_CUE.finditer(s) if any(ch.isdigit() for ch in m.group(1)))
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
_ISO_TS = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?")
_FI_TS = re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}\.\d{4}\s*(?:klo|kl\.?|at|,)?\s*(\d{1,2})[:.](\d{2})(?![\d])")


def raw_timestamps(s):
    n = 0
    for m in _ISO_TS.finditer(s):
        if m.group(2) != "00" or (m.group(3) and m.group(3) != "00"):
            n += 1
    for m in _FI_TS.finditer(s):
        if m.group(2) != "00":
            n += 1
    return n, 0


# --- 64-hex anywhere --------------------------------------------------------------------------
HEX64_ANY = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
HEX64_TOKEN = re.compile(r"[0-9a-f]{64}")


def hex64(s):
    return len(HEX64_ANY.findall(s)), 0
