"""Structured-label pass: validators and cue rules scored on the normalised view.

Order of work per conversation:
1. literal detectors on the original text (URL, e-mail, IP, MAC, property ID, plate) claim their
   regions; denylisted forms (dates/decimals, times, prices and amounts, version-like numbers,
   RFC1918/loopback IPs) are masked and never emitted;
2. spelled-out e-mails are reassembled from word tokens;
3. number runs (digits, spoken digits, letters, spoken separators) are classified with validators
   (HETU mod-31, IBAN mod-97, Luhn) and cue rules (4-digit card, account, PIN, IMEI);
4. N-turn joins: a run ending one turn and a run starting a later turn of the same speaker (window
   <= 3 turns, flushed at a non-continuation turn) are classified together; a validated value that
   crosses the boundary yields one span per turn fragment, sharing a placeholder key;
5. cue rules for SECRET and USERNAME take the value token after the cue.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from . import validators as V
from .labels import STRUCTURED_LABELS
from .normalise import Run, Sym, Token, tokenize, turn_runs
from .passes import PRIORITY_CUE, PRIORITY_VALIDATED, Candidate, ConversationView

JOIN_WINDOW = 3  # max turns a joined candidate may cover, first to last
HEAD_SLACK = 3  # word tokens allowed before a run that continues a previous turn
TAIL_SLACK = 2  # word tokens allowed after a run that continues in a later turn
CUE_WINDOW = 7  # words before a value searched for a cue

# ---- cue vocabularies (stems, matched with str.startswith on lower-cased words) ----
CARD_CUES = ("kortti", "kortil", "kortin", "korttia", "card", "kort", "päättyy", "loppuu", "ending", "ends",
             "slutar", "visa", "mastercard", "luottokort", "pankkikort")
ACCOUNT_CUES = ("asiakas", "lasku", "sopimus", "tilaus", "viite", "customer", "invoice", "contract", "order",
                "kundnum", "kundnr", "faktur", "avtal", "referen", "account", "konto", "asiakkuu", "tilin")
SECRET_CUES = ("tunnussana", "lösen", "passkod", "api", "apikey", "api-key", "token", "access", "secret",
               "salainen", "avain", "key", "pin", "puk", "salasan", "password", "passw", "lösenord", "koodi", "tunnusluku", "wifi", "wlan",
               "verkkoavain", "passcode", "kod", "nyckel",
               # one-time and card-verification codes, short forms (general fi/sv/en vocabulary)
               "pwd", "wi-fi", "wpa", "otp", "passphrase", "vahvistuskoodi", "varmennuskoodi", "kertakäyttö",
               "tekstiviestikoodi", "engångskod", "engångslösen", "verifieringskod", "bekräftelsekod", "cvv", "cvc",
               "cvn", "turvakoodi", "turvanumero", "säkerhetskod")
# "<qualifier> code" is a secret cue as a pair ('verification code', 'sms code'); the qualifier alone is not
CODE_QUALIFIERS = frozenset({"verification", "confirmation", "auth", "authentication", "sms", "login", "access",
                             "security", "one-time", "onetime", "2fa", "mfa"})
CODE_WORDS = frozenset({"code", "codes", "passcode", "pin"})
DEVICE_CUES = ("imei", "iccid", "sim", "sarjanumer", "serial", "serienummer", "laitetunnus", "laitteen")
USERNAME_CUES = ("käyttäjätunnu", "käyttäjänim", "username", "användarnamn", "login", "kirjautumistunnu",
                 "tunnukseni", "tunnuksella", "tunnukseen", "userid", "user-id", "user_id", "användar-id", "användarid")
HETU_CUES = ("hetu", "henkilötunnu", "henkilötunnukse", "personbeteckning", "personnummer", "personnumret", "identity",
             "personal", "sotu", "loppuosa", "tarkiste")
NUMBER_CUES = ("numero", "number", "nummer", "nro", "numret")
PLATE_CUES = ("auto", "rekisteri", "rekkari", "plate", "registration", "bil", "registrering", "ajoneuvo", "car")
VERSION_CUES = ("versio", "version", "firmware", "ohjelmisto", "päivitys", "update", "v")
FILLER = {"on", "oli", "is", "was", "är", "var", "my", "mun", "minun", "min", "mitt", "the", "varmaan", "probably",
          "nyt", "now", "se", "it", "s", "det", "nu", "kai", "siis", "edelleen", "still", "tällä", "hetkellä",
          "numero", "number", "nummer", "nro", "no", "koodi", "code", "salasana", "password", "lösenord",
          "lösenordet", "pin", "ja", "and", "och", "sitten", "then", "että", "that", "att", "ihan", "just",
          "vain", "only", "bara", "kuin"}

_TRAIL_PUNCT = ".,;:?)]}'\"»”"

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# a bare @handle (not an e-mail: nothing before the '@', no '.tld' after it)
_HANDLE_RE = re.compile(r"(?<![\w.@+-])@[A-Za-z][A-Za-z0-9_.]{2,29}(?![\w@-])(?!\.[A-Za-z]{2,})")
_IPV4_RE = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?![\w]|\.\d)")
# IPv6 candidates incl. compressed '::' forms; validity is decided by ipaddress, not the regex
_IPV6_RE = re.compile(r"(?<![\w:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w:])")
_MAC_RE = re.compile(r"(?<![\w:-])[0-9A-Fa-f]{2}(?:([:-])[0-9A-Fa-f]{2})(?:\1[0-9A-Fa-f]{2}){4}(?![\w:-])")
_PROPERTY_RE = re.compile(r"(?<![\w-])\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}(?![\w-])")
_PLATE_RE = re.compile(r"(?<![\w-])[A-Za-zÅÄÖåäö]{2,3}-\d{1,3}(?![\w-])")
_DOTTED_RE = re.compile(r"(?<![\w])\d+(?:[.,:]\d+)+\.?(?![\w])")
_EXPIRY_RE = re.compile(r"(?<![\w/])(?:0?[1-9]|1[0-2])/(?:\d{2}|20\d{2})(?![\w/])")
_TIME_RE = re.compile(r"(?i)\b(?:klo|kl\.?|at)\s*\d{1,2}(?:[.:]\d{2})?\b")
_CURRENCY = r"(?:€|eur|euro[a-zä]*|snt|sentti[a-zä]*|kr|kronor|sek|usd|\$|£|gbp|dollar[s]?)"
_AMOUNT_RE = re.compile(
    rf"(?i)(?:(?<![\w])\d+(?:[  ]\d{{3}})*(?:[.,]\d+)?(?:[.,]-)?\s?{_CURRENCY}(?![\w])"
    rf"|(?:€|\$|£)\s?\d+(?:[.,]\d+)?)"
)
_PERCENT_RE = re.compile(r"(?i)\d+(?:[.,]\d+)?\s?(?:%|prosentti[a-zä]*|procent|percent)")
_VERSION_RE = re.compile(r"(?i)\b(?:v|ver\.?|versio[a-zä]*|version|firmware[a-z]*)\s?:?\s?\d+(?:\.\d+)+")

AT_WORDS = {"at", "ät", "@", "snabel-a", "at-merkki", "kissanhäntä", "miukumauku", "ätt"}
DOT_WORDS = {"piste", "dot", "punkt", "pricken", "."}
JOIN_WORDS = {"alaviiva": "_", "underscore": "_", "understreck": "_", "viiva": "-", "väliviiva": "-",
              "dash": "-", "streck": "-", "bindestreck": "-", "hyphen": "-", "_": "_", "-": "-"}


@dataclass
class _Hit:
    turn_index: int
    start: int
    end: int
    label: str
    priority: int
    key: str | None


def _words_before(text: str, pos: int) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)?", text[:pos].lower())


def _context(view: ConversationView, turn_index: int, pos: int, n: int = CUE_WINDOW) -> list[str]:
    """Up to ``n`` words before ``pos`` in the turn, plus the last ``n`` words of the previous turn
    (an agent's question is the usual cue for a bare answer)."""
    words = _words_before(view.turns[turn_index].text, pos)[-n:]
    if turn_index > 0:
        prev = view.turns[turn_index - 1].text
        words = _words_before(prev, len(prev))[-n:] + words
    return words


HETU_TAIL_TURNS = 3
_HETU_TAIL_RE = re.compile(r"(?<![0-9A-Z])[-+A-FU-Y]\d{3}[0-9A-Y](?![0-9A-Z])")
_HETU_PARTIAL_RE = re.compile(r"\d{1,6}[-+A-FU-Y]\d{3}[0-9A-Y]")


def _wide_context(view: ConversationView, turn_index: int, pos: int, turns: int = HETU_TAIL_TURNS) -> list[str]:
    words: list[str] = []
    for k in range(max(0, turn_index - turns), turn_index):
        words += _words_before(view.turns[k].text, len(view.turns[k].text))
    return words + _words_before(view.turns[turn_index].text, pos)


def _has_cue(words: Iterable[str], cues: tuple[str, ...]) -> bool:
    """A word matches a cue stem; stems of <= 4 letters only match short inflections ('pin-koodi', 'kortet')."""
    for w in words:
        for c in cues:
            if len(c) == 1:
                if w == c:
                    return True
            elif w.startswith(c) and (len(c) > 4 or len(w) <= len(c) + 3 or w[len(c)] == "-"):
                return True
    return False


def _strip_trailing(text: str, start: int, end: int, chars: str = _TRAIL_PUNCT) -> int:
    while end > start and text[end - 1] in chars:
        end -= 1
    return end


class StructuredPass:
    """Validators and cue rules for the 13 structured labels."""

    name = "structured"
    labels = STRUCTURED_LABELS

    def __init__(self, join_window: int = JOIN_WINDOW) -> None:
        self.join_window = join_window

    # ------------------------------------------------------------------ public
    def run(self, view: ConversationView) -> Iterator[Candidate]:
        hits: list[_Hit] = []
        masks: list[list[tuple[int, int]]] = []
        email_groups: list[list[_Hit]] = []
        join_masks: list[list[tuple[int, int]]] = []  # masks without single-turn spelled e-mails
        for i, turn in enumerate(view.turns):
            m: list[tuple[int, int]] = []
            hits.extend(self._literals(view, i, m))
            join_masks.append(list(m))
            emails = self._spelled_emails(view, i, turn.text, m)
            email_groups.extend([h] for h in emails)
            hits.extend(self._cue_tokens(view, i, m))
            masks.append(m)
        runs = [turn_runs(i, t.text, masks[i]) for i, t in enumerate(view.turns)]
        # standalone and joined candidates compete as whole groups (see _resolve_groups): a split value
        # beats a standalone reading of one of its fragments unless that reading has a stronger validator
        groups: list[list[_Hit]] = []
        for rs in runs:
            for r in rs:
                groups.extend(self._classify(view, [r]))
        groups.extend(self._joins(view, runs))
        # a turn-local reading of part of an address competes with the joined reading (longest wins)
        groups.extend(email_groups)
        groups.extend(self._email_joins(view, join_masks))
        hits.extend(_resolve_groups(groups))
        hits.extend(self._hetu_tails(view, runs, hits))
        for h in hits:
            yield Candidate(h.turn_index, h.start, h.end, h.label, h.priority, h.key, self.name)

    # ------------------------------------------------------------- literals
    def _literals(self, view: ConversationView, i: int, masks: list[tuple[int, int]]) -> list[_Hit]:
        text = view.turns[i].text
        out: list[_Hit] = []

        def claim(s: int, e: int) -> None:
            masks.append((s, e))

        for m in _URL_RE.finditer(text):
            s, e = m.start(), _strip_trailing(text, m.start(), m.end(), _TRAIL_PUNCT + "!")
            claim(s, e)
            url = text[s:e]
            if ("?" in url and "=" in url) or "@" in url:
                out.append(_Hit(i, s, e, "URL", PRIORITY_VALIDATED, "url\x00" + url.lower()))
        for m in _EMAIL_RE.finditer(text):
            s, e = m.start(), _strip_trailing(text, m.start(), m.end(), ".-")
            if any(s >= a and e <= b for a, b in masks):
                continue
            claim(s, e)
            label = "USERNAME" if _has_cue(_context(view, i, s, 3), USERNAME_CUES) else "EMAIL"
            out.append(_Hit(i, s, e, label, PRIORITY_VALIDATED, "email\x00" + text[s:e].lower()))
        for m in _HANDLE_RE.finditer(text):
            s, e = m.start(), _strip_trailing(text, m.start(), m.end(), "._")
            if e - s < 4 or any(s < b and a < e for a, b in masks):
                continue
            claim(s, e)
            out.append(_Hit(i, s, e, "USERNAME", PRIORITY_CUE, "user\x00" + text[s:e].lower()))
        for m in _IPV4_RE.finditer(text):
            claim(m.start(), m.end())
            ip = m.group()
            if V.ipv4_personal(ip) and not _has_cue(_context(view, i, m.start(), 2), VERSION_CUES):
                out.append(_Hit(i, m.start(), m.end(), "IP_ADDRESS", PRIORITY_VALIDATED, "ip\x00" + ip))
        for m in _MAC_RE.finditer(text):
            claim(m.start(), m.end())
            out.append(_Hit(i, m.start(), m.end(), "DEVICE_ID", PRIORITY_VALIDATED, None))
        for m in _IPV6_RE.finditer(text):
            if any(m.start() < b and a < m.end() for a, b in masks):
                continue
            status = _ipv6_status(m.group())
            if status is None:
                continue  # not an address (e.g. a clock time)
            claim(m.start(), m.end())
            if status:
                out.append(_Hit(i, m.start(), m.end(), "IP_ADDRESS", PRIORITY_VALIDATED,
                                "ip6\x00" + status))
        for m in _APIKEY_RE.finditer(text):
            if any(m.start() < b and a < m.end() for a, b in masks):
                continue
            claim(m.start(), m.end())
            out.append(_Hit(i, m.start(), m.end(), "SECRET", PRIORITY_VALIDATED, None))
        for m in _PROPERTY_RE.finditer(text):
            claim(m.start(), m.end())
            out.append(_Hit(i, m.start(), m.end(), "PROPERTY_ID", PRIORITY_VALIDATED, None))
        for m in _PLATE_RE.finditer(text):
            letters = m.group().split("-")[0]
            if letters.lower() in ("klo", "kl"):
                continue
            claim(m.start(), m.end())
            if letters.isupper() or _has_cue(_context(view, i, m.start()), PLATE_CUES):
                out.append(_Hit(i, m.start(), m.end(), "LICENSE_PLATE", PRIORITY_CUE, None))
        # denylist: never emitted, and they break number runs
        for rx in (_VERSION_RE, _AMOUNT_RE, _PERCENT_RE, _DOTTED_RE, _TIME_RE, _EXPIRY_RE):
            for m in rx.finditer(text):
                if not any(m.start() >= a and m.end() <= b for a, b in masks):
                    claim(m.start(), m.end())
        return out

    # ------------------------------------------------------- spelled emails
    def _spelled_emails(self, view: ConversationView, i: int, text: str, masks) -> list[_Hit]:
        toks = _email_tokens(text, masks)
        out: list[_Hit] = []
        for lo, hi, addr in _email_matches(toks):
            s, e = toks[lo].start, toks[hi].end
            out.append(_Hit(i, s, e, "EMAIL", PRIORITY_VALIDATED, "email\x00" + addr))
            masks.append((s, e))
        return out

    def _email_joins(self, view: ConversationView, masks: list[list[tuple[int, int]]]) -> list[list[_Hit]]:
        """Spelled-out e-mails continued over later turns of the same speaker within the N-turn window
        (only backchannel turns of the other party in between; window <= join_window turns, first to
        last). Every accumulated window is matched as a whole; a match that touches more than one turn
        gives one span per turn and one shared key. A match is a contiguous token chain, so each part
        ends or starts its turn at the boundary it crosses."""
        turns = view.turns
        groups: list[list[_Hit]] = []
        toks_of = [_email_tokens(t.text, masks[k]) for k, t in enumerate(turns)]
        for i in range(len(turns)):
            if not toks_of[i]:
                continue
            flat: list[Token] = list(toks_of[i])
            owner: list[int] = [i] * len(toks_of[i])
            for j in range(i + 1, min(len(turns), i + self.join_window)):
                if turns[j].speaker != turns[i].speaker:
                    if not is_backchannel(turns[j].text):
                        break
                    continue
                if not toks_of[j]:
                    break
                flat += toks_of[j]
                owner += [j] * len(toks_of[j])
                for lo, hi, addr in _email_matches(flat):
                    touched = sorted(set(owner[lo:hi + 1]))
                    if len(touched) < 2 or touched[0] != i:
                        continue  # turn-local, or found again from a later start
                    # a typed '.' at either side of a turn boundary is sentence punctuation, not a dot-word
                    edges = [q for q in range(lo, hi) if owner[q] != owner[q + 1]]
                    if any(flat[q].text == "." or flat[q + 1].text == "." for q in edges):
                        continue
                    key = "email\x00" + addr
                    group = []
                    for k in touched:
                        idx = [q for q in range(lo, hi + 1) if owner[q] == k]
                        group.append(_Hit(k, flat[idx[0]].start, flat[idx[-1]].end, "EMAIL",
                                          PRIORITY_VALIDATED + 5, key))
                    groups.append(group)
        return groups

    # ------------------------------------------------------ SECRET/USERNAME
    def _cue_tokens(self, view: ConversationView, i: int, masks) -> list[_Hit]:
        text = view.turns[i].text
        out: list[_Hit] = []
        spans = _cue_scan_tokens(text)
        for idx, (s, e) in enumerate(spans):
            w = text[s:e].lower().strip(_TRAIL_PUNCT + "!")
            nxt = text[spans[idx + 1][0]:spans[idx + 1][1]].lower().strip(_TRAIL_PUNCT) if idx + 1 < len(spans) else ""
            label = None
            strong_phrase = False
            typo = False  # a misspelled password cue: only '<copula> <credential-shaped>' after it counts
            if any(c.isdigit() for c in w) and w.startswith(GLUED_SECRET_CUES) and _credential_shaped(w):
                # a cue word with digits glued on is itself a credential ('salasana123', 'pin1234')
                ve = _strip_trailing(text, s, e, _TRAIL_PUNCT + "!")
                if not any(s < b and a < ve for a, b in masks):
                    out.append(_Hit(i, s, ve, "SECRET", PRIORITY_CUE, None))
                continue
            start = idx + 1  # first token scanned for the value
            phrase = _phrase_cue(text, spans, idx)
            if phrase:
                label, start = "SECRET", idx + phrase  # 'one time code', 'personal identification number'
                strong_phrase = tuple(text[a:b].lower().strip(_TRAIL_PUNCT + "!")
                                      for a, b in spans[idx:start]) in STRONG_PHRASE_CUES
            elif w in CODE_QUALIFIERS and nxt in CODE_WORDS and text[s:e][-1] not in _SENTENCE_END:
                label = "SECRET"  # 'verification code', 'sms code' (the pair is the cue)
            elif _cue_word(w, SECRET_CUES):
                label = "SECRET"
            elif _cue_word(w, USERNAME_CUES):
                label = "USERNAME"
            elif (
                w == "user" and idx + 1 < len(spans) and text[spans[idx + 1][0]:spans[idx + 1][1]].lower() in ("name", "id")
            ):
                label = "USERNAME"
            elif _misspelled_password_cue(w):
                label, typo = "SECRET", True
            if label is None or text[spans[start - 1][0]:spans[start - 1][1]][-1] in _SENTENCE_END:
                continue
            # skip filler words and further cue words, take the next value token; ordinary words may sit
            # between cue and value ('salasana taitaa olla X'), then only a credential-shaped token counts
            intervening = 0
            for j in range(start, min(start + CUE_SCAN_TOKENS, len(spans))):
                vs, ve = spans[j]
                raw = text[vs:ve]
                low = raw.lower().strip(_TRAIL_PUNCT)
                # a token with a digit is a value even if it starts like a cue ('Salasana123')
                wordlike = not any(ch.isdigit() for ch in low)
                # fillers, the gate's copulas and hedges ('is maybe X', "it's X", 'probably:X' split in two)
                # and further cue words
                if wordlike and (low in FILLER or low in COPULAS or low.rstrip("=") in HEDGES or low in ("name", "id")
                                 or _cue_word(low, SECRET_CUES + USERNAME_CUES)) or not low or raw in (":", "-"):
                    if raw[-1] in _SENTENCE_END:
                        break  # the cue's sentence ended before any value
                    if low in COPULAS or raw.endswith((":", "=")):
                        intervening = 0  # the gate's rule: a later copula re-arms ('password for the router is X')
                    continue
                ve = _strip_trailing(text, vs, ve)
                val = text[vs:ve]
                if any(vs < b and a < ve for a, b in masks):
                    if _gate_date_or_time(val) and _copula_then_hedges(
                            text[s:e], [text[a:b] for a, b in spans[start:j]]):
                        # a copula-cued date or clock time is the value for the gate, although the denylist
                        # keeps it out of number runs ('wifi is 12:30', 'password is 12.03.2021')
                        out.append(_Hit(i, vs, ve, label, PRIORITY_CUE, None))
                    break
                prev = [text[a:b].lower().strip(_TRAIL_PUNCT) for a, b in spans[start:j]]
                # every cue word of the phrase counts ('wifi password is X': 'password' is the strong one)
                cue_words = [w] + [x for x in prev if _cue_word(x, SECRET_CUES + USERNAME_CUES)]
                if intervening:
                    ok = len(val) >= 5 and _credential_shaped(val)
                else:
                    # a digit, or the gate's credential shape (mixed case, inner symbol, long), with or without
                    # a copula ('password HunterTwo')
                    ok = (any(c.isdigit() for c in val) or (label == "USERNAME" and "@" in val)
                          or _credential_shaped(val))
                    if not ok and _alpha_credential(val, finnish=_has_cue(cue_words, FINNISH_CUES)):
                        # a plain word right after "<cue> <copula> [hedges]" is the value wherever the clause
                        # ends ('password is sunflower today'); network-key cues ('wifi is X') only when it ends
                        # the clause: mid-clause words after them are prose on the labelled train split
                        copula = _copula_then_hedges(text[s:e], [text[a:b] for a, b in spans[start:j]])
                        if label == "USERNAME" or strong_phrase or _has_cue(cue_words, STRONG_SECRET_CUES):
                            ok = copula or (label == "USERNAME" and j == start and _gate_username_word(val))
                        elif _has_cue(cue_words, NETWORK_KEY_CUES):
                            ok = copula and _clause_end(text, ve, spans, j, masks)
                        if ok:
                            # a credential-shaped token later in the same clause is the value, not this word
                            k = _credential_ahead(text, spans, j, start + CUE_SCAN_TOKENS, masks)
                            if k is not None:
                                # the plain word right after the copula is redacted too (the gate's rule counts
                                # it); the credential-shaped token is the value proper
                                out.append(_Hit(i, vs, ve, label, PRIORITY_CUE, None))
                                vs, ve = spans[k][0], _strip_trailing(text, spans[k][0], spans[k][1])
                                val = text[vs:ve]
                                if any(vs < b and a < ve for a, b in masks):
                                    break
                    if label == "SECRET" and val.isdigit():
                        # a PIN/code is 3-8 digits; a password-type cue takes any digit string ('salasana 482')
                        strong_digits = _has_cue(cue_words, PASSWORD_TYPE_CUES)
                        if len(val) < 3 or (len(val) > 8 and not strong_digits):
                            ok = False
                if typo:
                    ok = ok and _credential_shaped(val) and _copula_then_hedges(
                        text[s:e], [text[a:b] for a, b in spans[start:j]])
                if ok and len(val) >= 3:
                    # not masked: a validated identifier at the same place (HETU, phone) must still be found
                    # and outranks this cue-only reading in the pipeline's overlap resolution
                    out.append(_Hit(i, vs, ve, label, PRIORITY_CUE, None))
                    break
                if not wordlike or raw[-1] in _SENTENCE_END:
                    break
                # a word ending in ':' or '=' re-arms like a copula ('password for the router: X')
                intervening = 0 if raw.endswith((":", "=")) else intervening + 1
        return out

    # ------------------------------------------------------ run classifier
    def _classify(self, view: ConversationView, chain: list[Run], cross_only: bool = False) -> list[list[_Hit]]:
        """Validated/cued values in one run (or a cross-turn chain of runs); one group per value."""
        syms: list[Sym] = []
        owner: list[int] = []  # index into chain
        for ci, r in enumerate(chain):
            syms.extend(r.syms)
            owner.extend([ci] * len(r.syms))
        s = "".join(x.ch for x in syms)
        used = [False] * len(s)
        found: list[tuple[int, int, str, int, str]] = []  # a, b, label, priority, key

        def take(a: int, b: int, label: str, prio: int, key: str) -> None:
            for q in range(a, b):
                used[q] = True
            found.append((a, b, label, prio, key))

        for m in re.finditer(r"(?=(\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]))", s):
            a, b = m.start(1), m.end(1)
            # a following digit, or a letter glued to the same token, means this is not a whole HETU;
            # a separate word read as a letter name ('… är rätt') does not
            glued_after = b < len(s) and s[b].isalnum() and syms[b].tok == syms[b - 1].tok
            glued_before = a > 0 and s[a - 1].isalnum() and syms[a - 1].tok == syms[a].tok
            if any(used[a:b]) or glued_before or glued_after:
                continue
            if V.hetu_valid(s[a:b]):
                take(a, b, "NATIONAL_ID", PRIORITY_VALIDATED, "hetu\x00" + s[a:b])
        for m in re.finditer(r"(?=([A-Z]{2}\d{2}[0-9A-Z]{10,30}))", s):
            a = m.start(1)
            # no letter lookbehind: Swedish 'är' reads as the letter name R right before 'FI..'
            if any(used[a:a + 4]):
                continue
            for b in range(min(len(s), a + 34), a + 13, -1):
                if not any(used[a:b]) and V.iban_valid(s[a:b]):
                    take(a, b, "IBAN", PRIORITY_VALIDATED, "iban\x00" + s[a:b])
                    break
        def classify_segment(a: int, b: int) -> None:
            """Classify s[a:b] (unused symbols only); after any take, re-scan what is left of it."""
            while a < b and s[a] == "-":
                a += 1
            while b > a and s[b - 1] in "-+":
                b -= 1
            digits = s[a:b].replace("-", "").replace("+", "")
            if not digits:
                return
            ctx = _context(view, chain[owner[a]].turn_index, syms[a].start)
            # a line break inside the run (house number above, phone number on its own line): when the
            # part after the break is a phone by itself, it is not glued to the digits above it
            for q in range(a + 1, b):
                if owner[q] != owner[q - 1] or s[q] not in "0+":
                    continue
                gap = view.turns[chain[owner[q]].turn_index].text[syms[q - 1].end:syms[q].start]
                if "\n" not in gap:
                    continue
                tail = s[q:b].replace("-", "").replace("+", "")
                r_tail = _classify_digits(tail, s[q] == "+", ctx)
                if r_tail and r_tail[0] == "PHONE":
                    take(q, b, "PHONE", r_tail[1], _value_key("PHONE", tail, s[q] == "+"))
                    classify_segment(a, q)
                    return
            res = _classify_digits(digits, s[a] == "+", ctx)
            if res:
                take(a, b, res[0], res[1], _value_key(res[0], digits, s[a] == "+"))
                return
            # several values glued in one run ('Testitie 5 A 3 040 123 4567', 'IBAN + phone'): the longest
            # token-aligned sub-segment from the left that validates, then the remainder on both sides
            cuts = [q for q in range(a, b + 1)
                    if q in (a, b) or (syms[q].tok != syms[q - 1].tok and s[q - 1] != "-" and s[q] != "-")]
            for lo in cuts:
                for hi in reversed(cuts):
                    if hi <= lo or (lo, hi) == (a, b):
                        continue
                    sub = s[lo:hi].replace("-", "").replace("+", "")
                    r2 = _classify_digits(sub, s[lo] == "+", ctx)
                    if r2 and _sub_segment_ok(r2, syms[lo:hi], ctx):
                        take(lo, hi, r2[0], r2[1], _value_key(r2[0], sub, s[lo] == "+"))
                        classify_segment(a, lo)
                        classify_segment(hi, b)
                        return

        for m in re.finditer(r"\+?\d(?:-?\d)*", s):
            # split around symbols already taken (HETU, IBAN) and classify every unused stretch
            q = m.start()
            while q < m.end():
                if used[q]:
                    q += 1
                    continue
                r = q
                while r < m.end() and not used[r]:
                    r += 1
                classify_segment(q, r)
                q = r

        groups: list[list[_Hit]] = []
        for a, b, label, prio, key in found:
            owners = sorted(set(owner[a:b]))
            if cross_only:
                if len(owners) < 2:
                    continue
                # weak validators (Luhn: 1 in 10 random strings pass) need substantial fragments to join
                per = [sum(1 for q in range(a, b) if owner[q] == ci) for ci in owners]
                if min(per) < (4 if label in ("PAYMENT_CARD", "DEVICE_ID", "ACCOUNT_NUMBER") else 1):
                    continue
            group = []
            for ci in owners:
                idx = [q for q in range(a, b) if owner[q] == ci]
                first, last = syms[idx[0]], syms[idx[-1]]
                group.append(_Hit(chain[ci].turn_index, first.start, last.end, label,
                                  prio + (5 if len(owners) > 1 else 0), key))
            groups.append(group)
        return groups

    # ------------------------------------------------------ HETU tails
    def _hetu_tails(self, view: ConversationView, runs: list[list[Run]], hits: list[_Hit]) -> list[_Hit]:
        """A HETU tail on its own (century sign, 3 digits, check character): emitted when it repeats the
        tail of a HETU validated in this conversation (same placeholder), or when a HETU cue occurs in
        this or the previous HETU_TAIL_TURNS turns."""
        known = {h.key.split("\x00", 1)[1][-5:]: h.key for h in hits
                 if h.label == "NATIONAL_ID" and h.key and h.key.startswith("hetu\x00")}
        out: list[_Hit] = []
        for rs in runs:
            for r in rs:
                s = r.text
                for m in _HETU_TAIL_RE.finditer(s):
                    a, b = m.start(), m.end()
                    first, last = r.syms[a], r.syms[b - 1]
                    key = known.get(s[a:b])
                    if key is None and not _has_cue(_wide_context(view, r.turn_index, first.start), HETU_CUES):
                        continue
                    out.append(_Hit(r.turn_index, first.start, last.end, "NATIONAL_ID", PRIORITY_CUE,
                                    key or "hetu-tail\x00" + s[a:b]))
        return out

    def _partial_hetu(self, view: ConversationView, chain: list[Run]) -> list[list[_Hit]]:
        """Fragments that together end like a HETU (some leading digits, then the tail) after a HETU cue:
        one span per fragment. The joined value cannot be checksum-validated, so a cue is required."""
        s = "".join(r.text for r in chain)
        if not _HETU_PARTIAL_RE.fullmatch(s):
            return []
        r0 = chain[0]
        if not _has_cue(_wide_context(view, r0.turn_index, r0.syms[0].start), HETU_CUES):
            return []
        key = "hetu-partial\x00" + s
        return [[_Hit(r.turn_index, r.syms[0].start, r.syms[-1].end, "NATIONAL_ID", PRIORITY_CUE, key) for r in chain]]

    # ------------------------------------------------------ N-turn joins
    def _joins(self, view: ConversationView, runs: list[list[Run]]) -> list[list[_Hit]]:
        out: list[list[_Hit]] = []
        turns = view.turns
        for i, rs in enumerate(runs):
            if not rs or rs[-1].words_after > TAIL_SLACK:
                continue
            chain = [rs[-1]]
            speaker = turns[i].speaker
            for j in range(i + 1, min(len(turns), i + self.join_window)):
                if turns[j].speaker != speaker:
                    if not is_backchannel(turns[j].text):
                        break  # the other party said something else: flush
                    continue
                if not runs[j] or runs[j][0].words_before > HEAD_SLACK:
                    break
                chain = chain + [runs[j][0]]
                found = self._classify(view, chain, cross_only=True)
                out.extend(found)
                if not found:
                    out.extend(self._partial_hetu(view, chain))
                if len(runs[j]) > 1 or runs[j][0].words_after > TAIL_SLACK:
                    break
        return out


def _value_key(label: str, digits: str, plus: bool) -> str:
    """Placeholder key for a digit value; phones use the pseudonymiser's normaliser (ticket 06) so national
    and international forms of one number share a placeholder."""
    if label == "PHONE":
        from pets_release.pseudonym import normalise as pseudo_normalise

        if digits.startswith("00") and len(digits) >= 10 and not plus:  # international call prefix written as 00
            digits, plus = digits[2:], True

        return "phone\x00" + pseudo_normalise(("+" if plus or digits.startswith("358") else "") + digits, "PHONE")
    return label.lower() + "\x00" + digits


_CARD_GROUPS = ([4, 4, 4, 4], [4, 6, 5], [4, 4, 4, 4, 3])
_DEVICE_GROUPS = ([5, 5, 5], [2, 6, 6, 1])


def _sub_segment_ok(res: tuple[str, int], syms: list[Sym], ctx: list[str]) -> bool:
    """A sub-segment of a longer run is accepted for PHONE, or for a Luhn label when written in its standard
    grouping (one token, or 4-4-4-4 / 5-5-5 groups) or when a card/device cue is present: Luhn alone passes
    1 in 10 random sub-strings."""
    label, prio = res
    if label == "PHONE":
        return True
    if label not in ("DEVICE_ID", "PAYMENT_CARD") or prio != PRIORITY_VALIDATED:
        return False
    if _has_cue(ctx, DEVICE_CUES + CARD_CUES):
        return True
    groups: list[int] = []
    last = None
    for x in syms:
        if x.ch == "-":
            continue
        if x.tok != last:
            groups.append(0)
            last = x.tok
        groups[-1] += 1
    allowed = _CARD_GROUPS if label == "PAYMENT_CARD" else _DEVICE_GROUPS
    return (len(groups) == 1 and groups[0] >= 13) or groups in allowed


def _classify_digits(d: str, plus: bool, ctx: list[str]) -> tuple[str, int] | None:
    n = len(d)
    if plus and 8 <= n <= 15:
        return "PHONE", PRIORITY_VALIDATED  # '+' + country code: E.164 is at most 15 digits
    device = _has_cue(ctx, DEVICE_CUES)
    if 13 <= n <= 19 and V.luhn_valid(d):
        if device or (n == 15 and d[:2] not in ("34", "37")) or (n >= 18 and d.startswith("89")):
            return "DEVICE_ID", PRIORITY_VALIDATED
        if V.card_iin_plausible(d):
            return "PAYMENT_CARD", PRIORITY_VALIDATED
    if device and 14 <= n <= 20:
        return "DEVICE_ID", PRIORITY_CUE
    if d.startswith("358") and 11 <= n <= 13:
        return "PHONE", PRIORITY_VALIDATED
    if d.startswith("00358") and 13 <= n <= 15 and not plus:
        return "PHONE", PRIORITY_VALIDATED
    if d.startswith("0") and 7 <= n <= 11 and not plus:
        return "PHONE", PRIORITY_VALIDATED
    if d.startswith("00") and d[2:3] != "0" and 10 <= n <= 15 and not plus:
        return "PHONE", PRIORITY_VALIDATED  # international call prefix 00 + country code
    account = _has_cue(ctx, ACCOUNT_CUES)
    if account and 6 <= n <= 12:
        return "ACCOUNT_NUMBER", PRIORITY_CUE
    if n in (8, 10) and not d.startswith("0") and _has_cue(ctx, NUMBER_CUES):
        return "ACCOUNT_NUMBER", PRIORITY_CUE
    if n == 16 and _has_cue(ctx, CARD_CUES):
        return "PAYMENT_CARD", PRIORITY_CUE
    if n == 4 and _has_cue(ctx, CARD_CUES):
        return "PAYMENT_CARD", PRIORITY_CUE
    is_year = n == 4 and d[:2] in ("19", "20") and bool(ctx) and ctx[-1] in YEAR_WORDS
    if 4 <= n <= 8 and _has_cue(ctx, SECRET_CUES) and not is_year:
        return "SECRET", PRIORITY_CUE
    return None


BACKCHANNEL_MAX_WORDS = 4
# Acknowledgements and "go on" prompts (fi/sv/en, general language). Only turns made of these words
# continue an N-turn join; any other intervening turn of the other party flushes it.
BACKCHANNEL_WORDS = frozenset(["joo", "juu", "jep", "jees", "mm", "mmm", "mhm", "mm-m", "aha", "ahaa", "okei", "ok", "okay", "oki", "selvä", "selvä", "kyllä", "niin", "just", "jatka", "jatkakaa", "jatkat", "jatkatko", "kiitos", "hyvä", "no", "ja", "sitten", "loput", "entä", "seuraavaksi", "ok-ei", "yes", "yeah", "yep", "yup", "sure", "right", "alright", "uh-huh", "uh", "huh", "go", "on", "please", "thanks", "thank", "you", "and", "then", "the", "rest", "next", "got", "it", "ja", "jo", "javisst", "okej", "precis", "fortsätt", "tack", "bra", "och", "sen", "resten", "nästa", "mhm", "visst"])


def is_backchannel(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)?", text.lower())
    if re.search(r"\d", text) or len(words) > BACKCHANNEL_MAX_WORDS:
        return False
    return all(w in BACKCHANNEL_WORDS for w in words)


_SENTENCE_END = ".?!"
YEAR_WORDS = frozenset({"vuonna", "vuoden", "vuodesta", "vuoteen", "in", "since", "year", "år", "året", "sedan",
                        "från", "until", "asti", "saakka"})
CUE_SCAN_TOKENS = 6  # tokens after a SECRET/USERNAME cue searched for the value
# Common vendor key/token shapes (general knowledge): emitted without a cue.
_APIKEY_RE = re.compile(
    r"(?<![\w-])(?:(?:sk|pk|rk)[-_](?:live|test)[-_][A-Za-z0-9]{16,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})(?![\w-])")


def _credential_shaped(val: str) -> bool:
    """One token the gate counts as a credential: the gate's own definition (a digit, a letter with an inner
    symbol, mixed case, or 20+ alphanumerics; not a date or clock time), shared rather than copied."""
    from pets_release.checks.cells._validators import _credential_shaped as gate_credential_shaped

    return not re.search(r"\s", val) and gate_credential_shaped(val)


def _gate_username_word(val: str) -> bool:
    """A plain word directly after a username cue that the gate counts as the value (the gate's own rule,
    shared rather than copied: handle-shaped, 3-64 characters, not prose or a stop word)."""
    from pets_release.checks.text._detectors import _value_ok

    return _value_ok("username", 3, 64, val, False, False, True)


def _cue_word(w: str, cues: tuple[str, ...]) -> bool:
    """A token is a value cue: it matches a stem exactly, starts with a stem longer than 4 letters, or with a
    short stem followed by a non-letter ('pin-koodi', 'wpa2') or by an inflection ending ('wifin', 'pins'). A
    short stem that is otherwise a proper prefix of a longer word ('Pinja' for 'pin') is no cue."""
    for c in cues:
        if w == c or (w.startswith(c) and (len(c) > 4 or not w[len(c)].isalpha() or w[len(c):] in _INFLECTIONS)):
            return True
    return False


# fi/sv/en inflection endings after a short cue stem (general grammar: Finnish cases, Swedish definite and
# plural forms, English plural)
_INFLECTIONS = frozenset({"n", "a", "ä", "in", "iin", "ssa", "ssä", "sta", "stä", "lla", "llä", "lta", "ltä", "lle",
                          "ksi", "t", "en", "et", "er", "ar", "ens", "ets", "s"})


STRONG_SECRET_CUES = ("salasan", "password", "passw", "lösenord", "passphrase", "verkkoavain", "tunnuslause",
                      # every gate secret-type cue whose copula + plain word counts (text and cell rescans)
                      "pwd", "passcode", "tunnussana", "token", "api", "apikey", "api-key")
# network-key cues: a plain word after '<cue> <copula>' only when it ends the clause ('wifi is sunflower.');
# mid-clause words after them ('wifi is slow in the evening') are prose on the labelled train split
NETWORK_KEY_CUES = ("wifi", "wi-fi", "wlan", "wpa")
# Finnish cues: the Finnish past-participle endings ('vaihdettu', 'unohtunut') mark prose only after these
FINNISH_CUES = ("salasan", "tunnus", "käyttäjä", "kirjautumis", "verkkoavain", "wlan-avain", "koodi")
# multi-word cues; the scan for the value starts after the whole phrase
PHRASE_CUES = (("one", "time", "code"), ("one", "time", "password"), ("one", "time", "passcode"),
               ("one", "time", "pin"), ("personal", "identification", "number"), ("card", "verification", "value"),
               ("card", "verification", "code"), ("card", "security", "code"), ("secret", "key"))
# phrase cues after which '<copula> <plain word>' is the value, as after a strong cue (bare 'secret' is not)
STRONG_PHRASE_CUES = frozenset({("secret", "key")})


def _phrase_cue(text: str, spans: list[tuple[int, int]], idx: int) -> int:
    """Length in tokens of a multi-word cue starting at token ``idx`` (0 if none)."""
    for ph in PHRASE_CUES:
        if idx + len(ph) > len(spans):
            continue
        words = [text[a:b].lower().strip(_TRAIL_PUNCT + "!") for a, b in spans[idx:idx + len(ph)]]
        if tuple(words) == ph and not any(text[b - 1] in _SENTENCE_END for _a, b in spans[idx:idx + len(ph) - 1]):
            return len(ph)
    return 0


def _credential_ahead(text: str, spans: list[tuple[int, int]], j: int, stop: int, masks=()) -> int | None:
    """Index of a credential-shaped token (letters with digits/symbols/mixed case, or 3+ digits as the gate counts
    them; never a date or clock time) after token ``j`` in the same clause and scan window, or None. A comma does
    not end the clause: the gate's scan passes over it."""
    for k in range(j + 1, min(stop, len(spans))):
        if text[spans[k - 1][1] - 1] in _SENTENCE_END + ";":
            return None
        if any(spans[k][0] < b and a < spans[k][1] for a, b in masks):
            return None  # another identifier (e-mail, URL) ends the clause
        tok = text[spans[k][0]:_strip_trailing(text, spans[k][0], spans[k][1])]
        numeric = tok.isdigit() and len(tok) >= 3  # #54 r5: a digit-only credential counts too
        if (any(c.isalpha() for c in tok) or numeric) and _credential_shaped(tok):
            return k
    return None


# full password words (general fi/sv/en vocabulary) whose misspellings still cue a credential
TYPO_PASSWORD_CUES = ("password", "passphrase", "passcode", "salasana", "salasanani", "salasanasi", "tunnussana",
                      "lösenord", "lösenordet")


def _edit_distance(a: str, b: str, cap: int) -> int:
    """Levenshtein distance, stopping early once every cell of a row exceeds ``cap``."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _misspelled_password_cue(w: str) -> bool:
    """A word that is a misspelling of a password word: same first letter, within 1 edit (2 for words of 10+
    letters), and not the word itself (exact cues are handled by the cue vocabulary). 'passport' is 2 edits
    from 'password' and stays no cue."""
    if not (6 <= len(w) <= 14) or not w.isalpha():
        return False
    for c in TYPO_PASSWORD_CUES:
        cap = 2 if len(c) >= 10 else 1
        if w != c and w[0] == c[0] and abs(len(w) - len(c)) <= cap and _edit_distance(w, c, cap) <= cap:
            return True
    return False


def _gate_date_or_time(val: str) -> bool:
    """A date or clock time as the gate reads one after a copula (the gate's pattern, shared)."""
    from pets_release.checks import _cues

    return _cues.DATE_OR_TIME.fullmatch(val) is not None


def _cue_scan_tokens(text: str) -> list[tuple[int, int]]:
    """Whitespace tokens of a turn for the cue scan; a hedge glued to its value ('probably:X', 'nyt=X') is two
    tokens, the hedge with its delimiter and the value (the gate's own split, shared rather than copied)."""
    from pets_release.checks import _cues  # lazily, as elsewhere: the checks package loads the registry

    out = []
    for m in re.finditer(r"\S+", text):
        k = _cues.glued_hedge_len(m.group())
        out.extend([(m.start(), m.start() + k), (m.start() + k, m.end())] if k else [(m.start(), m.end())])
    return out


def _copula_then_hedges(cue_tok: str, between: list[str]) -> bool:
    """A copula or colon between cue and value, followed by nothing but hedges ('password is probably X');
    any other word after the copula ('is the X', 'is not X') makes the plain word a description."""
    words = [t.lower().strip(_TRAIL_PUNCT) for t in between]
    raw = [t for t in between]
    cop = [k for k, (wd, r) in enumerate(zip(words, raw)) if wd in COPULAS or r.endswith((":", "="))]
    if not cop:
        return cue_tok.endswith(":") and all(wd in HEDGES for wd in words)
    return all(wd in HEDGES for wd in words[cop[-1] + 1:])
GLUED_SECRET_CUES = STRONG_SECRET_CUES + ("pin", "puk", "salasana")
# password-type and network-key cues: a digit value after one may be longer than a PIN ('salasana 48213579')
PASSWORD_TYPE_CUES = STRONG_SECRET_CUES + ("pwd", "lösen", "tunnussana", "wifi", "wi-fi", "wlan", "wpa")
# at least the gate's copulas and hedges (checks._cues; a test pins the superset)
COPULAS = frozenset({"on", "oli", "is", "was", "är", "var", "it's", "its", ":", "="})
HEDGES = frozenset({"varmaan", "kai", "luultavasti", "ehkä", "probably", "maybe", "perhaps", "still", "edelleen",
                    "nog", "kanske", "typ", "fortfarande", "nyt", "now", "nu"})
# Words that commonly follow "password is / salasana on / lösenordet är" as prose, not as the value
# (general-language list, not derived from the kit).
CREDENTIAL_PROSE = frozenset(["not", "no", "none", "never", "ei", "eikä", "inte", "icke", "wrong", "incorrect", "invalid", "expired", "changed", "correct", "right", "ok", "okay", "fine", "working", "broken", "locked", "blocked", "lost", "forgotten", "unknown", "new", "old", "same", "different", "too", "very", "still", "also", "just", "really", "väärä", "oikea", "vanha", "uusi", "sama", "eri", "liian", "tosi", "vielä", "edelleen", "myös", "vain", "hukassa", "lukossa", "voimassa", "vanhentunut", "vaihdettu", "unohtunut", "kadonnut", "estetty", "jotain", "mikä", "mitä", "tämä", "tuo", "sinun", "teidän", "minun", "hyvä", "huono", "pitkä", "lyhyt", "fel", "rätt", "gammal", "gamla", "ny", "nya", "samma", "annan", "för", "mycket", "fortfarande", "också", "bara", "glömt", "ändrat", "borta", "låst", "spärrat", "något", "vad", "detta", "det", "din", "ditt", "er", "bra", "dålig", "lång", "kort", "the", "a", "an", "my", "your", "this", "that", "what", "something", "required", "needed",
    # function words and service-desk prose that follow a cue without being its value (general fi/sv/en)
    "with", "from", "into", "about", "after", "before", "again", "when", "where", "which", "while", "here",
    "there", "please", "thanks", "thank", "have", "does", "doesn", "didn", "isn", "wasn", "should", "would",
    "could", "will", "cannot", "also", "only", "even", "then", "than", "page", "screen", "field", "details",
    "info", "information", "problem", "problems", "issue", "issues", "reset", "change", "link", "account",
    "service", "portal", "login", "user", "name", "username", "password", "code", "number", "missing",
    "kanssa", "jolla", "joka", "jota", "jonka", "mutta", "koska", "että", "vielä", "taas", "uudelleen", "toimi",
    "toimii", "toimiva", "sivu", "sivulle", "sivulla", "kenttä", "kenttään", "ongelma", "ongelmia", "nollaus",
    "vaihto", "tili", "tilin", "palvelu", "palveluun", "tunnus", "tunnukset", "salasana", "sekä",
    "till", "från", "eller", "fungerar", "sidan", "problem", "kontot", "tjänsten", "användarnamn", "lösenord"])


def _clause_end(text: str, ve: int, spans: list[tuple[int, int]], j: int, masks) -> bool:
    """The value ends its clause: end of turn, closing punctuation, or the next token is itself an identifier
    the redactor claims (a masked literal, an e-mail, or a number). A next token mixing letters and digits is
    not a clause end: it is the more likely value ('password is now-ish Kissa2024')."""
    rest = text[ve:]
    if rest.strip() == "" or rest.lstrip()[:1] in ".,;!?)\"'":
        return True
    if j + 1 >= len(spans):
        return True
    ns, ne = spans[j + 1]
    nxt = text[ns:ne].strip(_TRAIL_PUNCT)
    if any(ns < b and a < ne for a, b in masks) or "@" in nxt:
        return True
    return bool(nxt) and re.fullmatch(r"\+?[\d\s()-]+", nxt) is not None


def _alpha_credential(val: str, finnish: bool = False) -> bool:
    """A plain-word credential after a cue: one token of 3-32 characters that is not a prose word (the
    redactor's list plus the gate's shared list, ``checks._cues.PROSE_WORDS``) and, after a Finnish cue, not
    a Finnish past participle ('vaihdettu', 'unohtunut'). No English suffix guess: 'alfred' is a name."""
    from pets_release.checks._cues import PROSE_WORDS as GATE_PROSE

    low = val.lower()
    if not (3 <= len(val) <= 32) or not re.fullmatch(r"[^\W\d_][\w!#$%&*+\-.@]*", val):
        return False
    if low in CREDENTIAL_PROSE or low in FILLER or low in GATE_PROSE or low in _PROSE_EXTRA:
        return False
    return not (finnish and re.search(r"(?:ttu|tty|nut|nyt|ttiin|tetty|tettu)$", low))


# Whole words (no suffix rules) that follow 'password was ...' as prose: adverbs and English participles
_PROSE_EXTRA = frozenset(["last", "already", "updated", "sent", "saved", "stored", "encrypted", "hidden",
                          "shared", "case-sensitive"])


def _email_tokens(text: str, masks) -> list[Token]:
    """Unmasked tokens of a turn, with 'snabel-a' / 'at-merkki' style words merged into one token."""
    toks = [t for t in tokenize(text) if not any(t.start < b and a < t.end for a, b in masks)]
    merged: list[Token] = []
    j = 0
    while j < len(toks):
        t = toks[j]
        if (j + 2 < len(toks) and toks[j + 1].text == "-" and toks[j + 1].start == t.end
                and toks[j + 2].start == toks[j + 1].end):
            cand = (t.text + "-" + toks[j + 2].text).lower()
            if cand in AT_WORDS:
                merged.append(Token(t.index, t.start, toks[j + 2].end, cand))
                j += 3
                continue
        merged.append(t)
        j += 1
    return merged


def _email_matches(toks: list[Token]) -> list[tuple[int, int, str]]:
    """Spelled-out addresses: local part (word (joiner word)*) + at-word + domain (word (joiner word)+ with
    at least one dot-word). Returns (first token index, last token index, assembled address)."""
    out: list[tuple[int, int, str]] = []
    for k, t in enumerate(toks):
        if t.text.lower() not in AT_WORDS or t.text == "@":
            continue
        left = k - 1
        if left < 0 or not _is_email_word(toks[left]):
            continue
        parts = [toks[left].text]
        while left - 2 >= 0 and _joiner(toks[left - 1]) and _is_email_word(toks[left - 2]):
            parts = [toks[left - 2].text, _joiner(toks[left - 1])] + parts
            left -= 2
        right = k + 1
        if right >= len(toks) or not _is_email_word(toks[right]):
            continue
        dom = [toks[right].text]
        ndots = 0
        while right + 2 < len(toks) and _joiner(toks[right + 1]) and _is_email_word(toks[right + 2]):
            if toks[right + 1].text.lower() in DOT_WORDS:
                ndots += 1
            dom += [_joiner(toks[right + 1]), toks[right + 2].text]
            right += 2
        if ndots == 0:
            continue
        out.append((left, right, ("".join(parts) + "@" + "".join(dom)).lower()))
    return out


def _strength(h: _Hit) -> int:
    """Validator strength for resolving standalone vs joined candidates: checksum (HETU mod-31, IBAN
    mod-97) > Luhn > structure-only (phone, e-mail, ...) > cue-only."""
    if h.priority < PRIORITY_VALIDATED:
        return 0
    return {"NATIONAL_ID": 3, "IBAN": 3, "PAYMENT_CARD": 2, "DEVICE_ID": 2}.get(h.label, 1)


def _resolve_groups(groups: list[list[_Hit]]) -> list[_Hit]:
    """Pick non-overlapping groups (a group = all fragments of one value). Stronger validator first,
    then the longest span across the window, then earliest position. A group is kept or dropped whole."""
    order = sorted(groups, key=lambda g: (-max(_strength(h) for h in g), -sum(h.end - h.start for h in g),
                                          min((h.turn_index, h.start) for h in g), len(g)))
    taken: dict[int, list[tuple[int, int]]] = {}
    out: list[_Hit] = []
    for g in order:
        if any(h.start < e and s < h.end for h in g for s, e in taken.get(h.turn_index, [])):
            continue
        for h in g:
            taken.setdefault(h.turn_index, []).append((h.start, h.end))
        out.extend(g)
    return out


def _is_email_word(t: Token) -> bool:
    low = t.text.lower()
    return t.text[0].isalnum() and low not in AT_WORDS and low not in DOT_WORDS and low not in JOIN_WORDS


def _joiner(t: Token) -> str | None:
    low = t.text.lower()
    if low in DOT_WORDS:
        return "."
    return JOIN_WORDS.get(low)


def _ipv6_status(s: str) -> str | None:
    """None if not an IPv6 address; '' if valid but not personal (loopback, link-local, ULA, other
    non-global); else the compressed canonical form (so '::'-compressed and full forms share a key)."""
    import ipaddress

    try:
        ip = ipaddress.IPv6Address(s)
    except ValueError:
        return None
    return ip.compressed if ip.is_global else ""
