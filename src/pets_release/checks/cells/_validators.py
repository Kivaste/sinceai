"""Independent identifier validators for the gate (no shared code with detector or redactor).

Each finder takes one cell string and returns (high, low): how many matches of each severity.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

import pets_release.checks._cues as _cues

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
_PSEP = r"(?:,[ \t]?|[\s-])"  # one separator: whitespace, a dash, or a comma (#56: spoken phones)
_PHONE = re.compile(
    r"(?<![\w+])(?:(?:\+|00)[1-9]\d{0,2}" + _PSEP + r"?(?:\(0\)" + _PSEP + r"?)?(?:\d" + _PSEP + r"?){5,12}\d"
    r"|0(?:4\d|50)(?:" + _PSEP + r"?\d){5,8}"
    r"|0[1-9]\d?" + _PSEP + r"\d{3,4}" + _PSEP + r"?\d{2,4})(?![\w.,]\d|\w)")


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
# Scanned over up to _cues.WINDOW tokens after the cue, never past a sentence end (". ! ? ;"):
# * a credential-shaped token (digit, inner symbol, mixed case, long) counts anywhere in the scan;
# * a copula ("is", "on", "är", ":", "=", also a trailing ":" as in "router: x") arms; while armed, the first
#   word that is not a hedge (_cues.HEDGES) is the value: it counts unless it is prose (a date counts too).
#   Any copula later in the scan re-arms ("password for the router is kissakala");
# * function words other than hedges ("is a pain", "is not working") and any other non-value word disarm;
# * separator/punctuation runs ("-", "--", "/", "#", "·") are skipped;
# * an exact redactor placeholder is the (already redacted) value: skipped, and it disarms, unless a
#   value is glued to it ("[SECRET_1]hunterxyz");
# * a plain word directly before a placeholder is not the value (the placeholder is); after a bare
#   wifi/wlan cue a plain word counts only at the clause end;
# * a cue inside a placeholder ("[USERNAME_1]") is no cue; a cue glued to a longer word ("pinta") is no cue.
# Brackets are value characters ("[Hunter2!]"), not a placeholder.
_CUE_TOKEN = re.compile(_cues.PLACEHOLDER_SRC + r"|(?:(?!" + _cues.PLACEHOLDER_SRC + r")\S)+")
_WRAP = "\"'()[]<>,;"
_SENTENCE_END = ".!?;"
_DATE_OR_TIME = _cues.DATE_OR_TIME


def _credential_shaped(v: str) -> bool:
    core = v.rstrip(".!?)")
    if len(core) < 3 or _DATE_OR_TIME.fullmatch(core):
        return False
    has_l = any(c.isalpha() for c in core)
    has_d = any(c.isdigit() for c in core)
    inner_sym = any(c in "!#$%&*+=?@_~^/\\" for c in core)
    mixed = any(c.isupper() for c in core[1:]) and any(c.islower() for c in core)
    return has_d or (inner_sym and has_l) or mixed or (len(core) >= 20 and core.isalnum())


# a bare network cue (no key/password suffix) is about the network; its plain-word "value" mid-clause is
# prose ("wifi is terrible today"); credential-shaped tokens and a clause-final word still count
_BARE_NETWORK_CUE = re.compile(r"(?i)wi-?fi|wlan")


def _split_glued_hedge(start: int, tok: str):
    """A hedge glued to its value ("probably:<value>", "nyt=<value>") is two tokens: the hedge with its
    trailing delimiter (which arms) and the remainder (judged as the value)."""
    k = _cues.glued_hedge_len(tok)
    if not k:
        return [(start, start + len(tok), tok)]
    return [(start, start + k, tok[:k]), (start + k, start + len(tok), tok[k:])]


def _cued_values(cue, s: str, *, alpha_without_copula: bool) -> int:
    """Cue matches in ``s`` followed by a value; a cue inside a placeholder ("[USERNAME_1]") is no cue."""
    ph = [m.span() for m in _cues.PLACEHOLDER_RE.finditer(s)]
    return sum(1 for m in cue.finditer(s)
               if not any(a <= m.start() < b for a, b in ph)
               and _cued_value_counts(s, m.end(), alpha_without_copula=alpha_without_copula,
                                      plain_mid_clause_is_prose=bool(_BARE_NETWORK_CUE.fullmatch(m.group(0)))))


def _cued_value_counts(s: str, pos: int, *, alpha_without_copula: bool,
                       plain_mid_clause_is_prose: bool = False) -> bool:
    """True when a value follows the cue ending at ``pos``. ``alpha_without_copula``: a plain word right
    after the cue counts too (usernames: "username mattikoski")."""
    armed = False  # a copula, followed by nothing but hedges, separators or a glued placeholder
    words = 0
    toks = []  # (start, end, text)
    for m in _CUE_TOKEN.finditer(s, pos):
        toks.extend(_split_glued_hedge(m.start(), m.group(0)))
        if len(toks) > _cues.WINDOW:
            break
    for i, (start, end, tok) in enumerate(toks[:_cues.WINDOW]):
        nxt = toks[i + 1][2] if i + 1 < len(toks) else None
        if i == 0 and start == pos and tok[0].isalpha():
            return False  # the cue is the start of another word ("pinta", "passwordless")
        if _cues.is_placeholder(tok):
            if not s[end:end + 1].isalnum():
                armed = False  # the redacted value took the copula; "[SECRET_1] ok" is prose
            continue
        if tok[:1] in ":=":
            armed = True
        core = tok.lstrip(":=")
        last = core.rstrip("\"')]")[-1:]
        ends = bool(last) and last in _SENTENCE_END
        val = core.strip(_WRAP)
        word = val.rstrip(".!?:=)")
        low = word.lower()
        arms_after = val.rstrip(".!?)")[-1:] in (":", "=") and not ends  # "router: x", "pwd= x"
        if _cues.is_punct(word):
            if ends:
                break
            armed = armed or arms_after
            continue
        first_word = words == 0
        words += 1
        if low in _cues.COPULAS:
            armed = True
            continue
        if low in _cues.HEDGES:
            if ends:
                break
            armed = armed or arms_after  # "password probably: x"
            continue
        if low in _cues.FUNCTION_WORDS:
            armed = arms_after  # "is a pain", "is not working": a description, not a value
            if ends:
                break
            continue
        if _credential_shaped(val):
            return True
        if armed and _DATE_OR_TIME.fullmatch(word):
            # a copula-cued date/time is a value, also directly before or glued to a placeholder, and
            # also mid-clause after a bare network cue (only a plain word there is prose)
            return True
        plain_ok = (
            # (b) a plain word directly before a placeholder is not the value: the placeholder is
            not (nxt is not None and _cues.is_placeholder(nxt))
            # (c) after a bare wifi/wlan cue a plain word counts only at the clause end ("wifi: x")
            and not (plain_mid_clause_is_prose and not ends and nxt is not None
                     and not _cues.is_punct(nxt)))
        if plain_ok and (armed or (alpha_without_copula and first_word)) and low not in _cues.PROSE_WORDS and (
                (len(word) >= 3 and any(c.isalpha() for c in word))
                or (armed and _DATE_OR_TIME.fullmatch(word))):
            return True
        if ends:
            break
        armed = arms_after  # any other word is not the value; a later copula re-arms
    return False


# --- usernames (cue + handle, or @handle not part of an email) ---------------------------------
_USER = re.compile(
    r"(?i)\b(?:käyttäjätunnu(?:s|ksella|ksen|kseni)|käyttäjänimi|tunnukse(?:ni|lla|en)|username|user\s?name|"
    r"login|user\s?id|användarnamn|användar-?id)")
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_]{3,30})(?![\w@.]*\.[A-Za-z]{2,})")


def usernames(s):
    # the cue is required; after a copula/colon a purely alphabetic value counts, without one only a
    # credential-shaped or non-prose value does (the shape the redactor uses)
    n = _cued_values(_USER, s, alpha_without_copula=True)
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
    r"wi-?fi(?:-?avain|-?salasana|\s?key|\s?password)?|wlan(?:-?avain)?|wpa\d?)")


def secrets(s):
    n = len(_KEYSHAPES.findall(s))
    # cue + (copula|colon) + value, or cue + a credential-shaped token (digit, symbol, mixed case, long);
    # cued everyday words ("password for the router", "password reset") are not values
    n += _cued_values(_SECRET_CUE, s, alpha_without_copula=False)
    return n, 0


# --- URLs carrying tokens ---------------------------------------------------------------------
_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'\]]+")  # scheme-less www. too (#56)
_TOKEN_KEYS = {"token", "access_token", "auth", "key", "apikey", "api_key", "sig", "signature", "session", "sid",
               "code", "otp", "reset", "password", "pwd", "email", "user", "uid", "jwt", "secret"}
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{24,}$")


def _url_has_token(u: str) -> bool:
    u = u.rstrip(".,;:)")
    try:
        parts = urlsplit(u if "://" in u else "http://" + u)
    except ValueError:
        return True  # unparseable URL: treat as suspicious
    # the fragment is parsed like the query and path (#56): "#token=...", "#/cb?code=...", "#/reset/<token>"
    frag_path, _, frag_query = parts.fragment.partition("?")
    queries = (parts.query, frag_query, frag_path if "=" in frag_path else "")
    for k, v in (kv for q in queries for kv in parse_qsl(q, keep_blank_values=True)):
        if k.lower().lstrip("/") in _TOKEN_KEYS or "@" in v or (_OPAQUE.match(v) and any(c.isdigit() for c in v)):
            return True
    if parts.username or parts.password:
        return True
    for seg in parts.path.split("/") + re.split(r"[/=&]", parts.fragment):
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
