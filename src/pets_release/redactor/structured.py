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
SECRET_CUES = ("pin", "puk", "salasan", "password", "passw", "lösenord", "koodi", "tunnusluku", "wifi", "wlan",
               "verkkoavain", "passcode", "kod", "nyckel")
DEVICE_CUES = ("imei", "iccid", "sim", "sarjanumer", "serial", "serienummer", "laitetunnus", "laitteen")
USERNAME_CUES = ("käyttäjätunnu", "käyttäjänim", "username", "användarnamn", "login", "kirjautumistunnu")
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
        for i, turn in enumerate(view.turns):
            m: list[tuple[int, int]] = []
            hits.extend(self._literals(view, i, m))
            hits.extend(self._spelled_emails(view, i, turn.text, m))
            hits.extend(self._cue_tokens(view, i, m))
            masks.append(m)
        runs = [turn_runs(i, t.text, masks[i]) for i, t in enumerate(view.turns)]
        single: list[_Hit] = []
        for i, rs in enumerate(runs):
            for r in rs:
                single.extend(self._classify(view, [r]))
        hits.extend(single)
        # symbols inside a validated single-turn value are not available to cross-turn joins
        claimed = {(h.turn_index, p) for h in single if h.priority >= PRIORITY_VALIDATED for p in range(h.start, h.end)}
        hits.extend(self._joins(view, runs, claimed))
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
        toks = [t for t in tokenize(text) if not any(t.start < b and a < t.end for a, b in masks)]
        # merge 'snabel-a' / 'at-merkki' style tokens: word '-' word with no spaces
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
        toks = merged
        out: list[_Hit] = []
        for k, t in enumerate(toks):
            if t.text.lower() not in AT_WORDS or t.text == "@":
                continue
            # local part: word (joiner word)* ending just before the at-word
            left = k - 1
            if left < 0 or not _is_email_word(toks[left]):
                continue
            parts = [toks[left].text]
            while left - 2 >= 0 and _joiner(toks[left - 1]) and _is_email_word(toks[left - 2]):
                parts = [toks[left - 2].text, _joiner(toks[left - 1])] + parts
                left -= 2
            # domain: word (dot-word word)+
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
            s, e = toks[left].start, toks[right].end
            addr = ("".join(parts) + "@" + "".join(dom)).lower()
            out.append(_Hit(i, s, e, "EMAIL", PRIORITY_VALIDATED, "email\x00" + addr))
            masks.append((s, e))
        return out

    # ------------------------------------------------------ SECRET/USERNAME
    def _cue_tokens(self, view: ConversationView, i: int, masks) -> list[_Hit]:
        text = view.turns[i].text
        out: list[_Hit] = []
        spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        for idx, (s, e) in enumerate(spans):
            w = text[s:e].lower().strip(_TRAIL_PUNCT + "!")
            label = None
            if _has_cue([w], SECRET_CUES):
                label = "SECRET"
            elif _has_cue([w], USERNAME_CUES) or (
                w == "user" and idx + 1 < len(spans) and text[spans[idx + 1][0]:spans[idx + 1][1]].lower() in ("name", "id")
            ):
                label = "USERNAME"
            if label is None or text[s:e][-1] in _SENTENCE_END:
                continue
            # skip filler words and further cue words, take the next value token
            for j in range(idx + 1, min(idx + 5, len(spans))):
                vs, ve = spans[j]
                raw = text[vs:ve]
                low = raw.lower().strip(_TRAIL_PUNCT)
                # a token with a digit is a value even if it starts like a cue ('Salasana123')
                wordlike = not any(ch.isdigit() for ch in low)
                if wordlike and (low in FILLER or low in ("name", "id")
                                 or _has_cue([low], SECRET_CUES + USERNAME_CUES)) or not low or raw in (":", "-"):
                    if raw[-1] in _SENTENCE_END:
                        break  # the cue's sentence ended before any value
                    continue
                ve = _strip_trailing(text, vs, ve)
                val = text[vs:ve]
                if any(vs < b and a < ve for a, b in masks):
                    break
                ok = any(c.isdigit() for c in val) or (label == "USERNAME" and "@" in val)
                if not ok and _alpha_credential(val):
                    # alphabetic values only in the shape "<password-type cue> <copula> [hedge] VALUE<end of clause>"
                    prev = [text[a:b].lower().strip(_TRAIL_PUNCT) for a, b in spans[idx + 1:j]]
                    strong = label == "USERNAME" or _has_cue([w], STRONG_SECRET_CUES)
                    copula = (not prev and text[s:e].endswith(":")) or bool(prev) and (prev[-1] in COPULAS or (len(prev) >= 2 and prev[-1] in HEDGES
                                                                     and prev[-2] in COPULAS))
                    rest = text[ve:]
                    clause_end = rest.strip() == "" or rest.lstrip()[:1] in ".,;!?)\"'"
                    ok = strong and copula and clause_end
                if label == "SECRET" and val.isdigit() and not (4 <= len(val) <= 8):
                    ok = False
                if ok and len(val) >= 3:
                    out.append(_Hit(i, vs, ve, label, PRIORITY_CUE, None))
                    masks.append((vs, ve))
                break
        return out

    # ------------------------------------------------------ run classifier
    def _classify(self, view: ConversationView, chain: list[Run], cross_only: bool = False,
                  claimed: frozenset | set = frozenset()) -> list[_Hit]:
        syms: list[Sym] = []
        owner: list[int] = []  # index into chain
        for ci, r in enumerate(chain):
            syms.extend(r.syms)
            owner.extend([ci] * len(r.syms))
        s = "".join(x.ch for x in syms)
        used = [(chain[owner[q]].turn_index, syms[q].start) in claimed for q in range(len(s))]
        found: list[tuple[int, int, str, int, str]] = []  # a, b, label, priority, key

        def take(a: int, b: int, label: str, prio: int, key: str) -> None:
            for q in range(a, b):
                used[q] = True
            found.append((a, b, label, prio, key))

        for m in re.finditer(r"(?=(\d{6}[-+A-FU-Y]\d{3}[0-9A-Y]))", s):
            a, b = m.start(1), m.end(1)
            # a following digit, or a letter glued to the same token, means this is not a whole HETU;
            # a separate word read as a letter name ('… är rätt') does not
            glued_after = b < len(s) and (s[b].isdigit() or (s[b].isalpha() and syms[b].tok == syms[b - 1].tok))
            if any(used[a:b]) or (a > 0 and s[a - 1].isdigit()) or glued_after:
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
        for m in re.finditer(r"\+?\d(?:-?\d)*", s):
            a, b = m.start(), m.end()
            if any(used[a:b]):
                continue
            digits = s[a:b].replace("-", "").replace("+", "")
            first_turn = chain[owner[a]].turn_index
            ctx = _context(view, first_turn, syms[a].start)
            res = _classify_digits(digits, s[a] == "+", ctx)
            if res:
                take(a, b, res[0], res[1], res[0].lower() + "\x00" + digits)
                continue
            # a typed value glued to a neighbouring number ('Testitie 5 A 3 040 123 4567'): retry
            # sub-segments that start and end on token boundaries, validated labels only
            cuts = [q for q in range(a, b + 1)
                    if q in (a, b) or (syms[q].tok != syms[q - 1].tok and s[q - 1] != "-" and s[q] != "-")]
            done = False
            for lo in cuts:
                for hi in reversed(cuts):
                    if hi <= lo or (lo, hi) == (a, b) or done:
                        continue
                    sub = s[lo:hi].replace("-", "")
                    r2 = _classify_digits(sub, False, ctx)
                    # Luhn passes 1 in 10 random sub-strings: card/device sub-segments need their cue
                    if r2 and (r2[0] == "PHONE" or (r2[0] in ("DEVICE_ID", "PAYMENT_CARD") and r2[1] == PRIORITY_VALIDATED
                                                    and _has_cue(ctx, DEVICE_CUES + CARD_CUES))):
                        take(lo, hi, r2[0], r2[1], r2[0].lower() + "\x00" + sub)
                        done = True
                if done:
                    break

        hits: list[_Hit] = []
        for a, b, label, prio, key in found:
            owners = sorted(set(owner[a:b]))
            if cross_only:
                if len(owners) < 2:
                    continue
                # weak validators (Luhn: 1 in 10 random strings pass) need substantial fragments to join
                per = [sum(1 for q in range(a, b) if owner[q] == ci) for ci in owners]
                if min(per) < (4 if label in ("PAYMENT_CARD", "DEVICE_ID", "ACCOUNT_NUMBER") else 1):
                    continue
            for ci in owners:
                idx = [q for q in range(a, b) if owner[q] == ci]
                first, last = syms[idx[0]], syms[idx[-1]]
                hits.append(_Hit(chain[ci].turn_index, first.start, last.end, label,
                                 prio + (5 if len(owners) > 1 else 0), key))
        return hits

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

    def _partial_hetu(self, view: ConversationView, chain: list[Run]) -> list[_Hit]:
        """Fragments that together end like a HETU (some leading digits, then the tail) after a HETU cue:
        one span per fragment. The joined value cannot be checksum-validated, so a cue is required."""
        s = "".join(r.text for r in chain)
        if not _HETU_PARTIAL_RE.fullmatch(s):
            return []
        r0 = chain[0]
        if not _has_cue(_wide_context(view, r0.turn_index, r0.syms[0].start), HETU_CUES):
            return []
        key = "hetu-partial\x00" + s
        return [_Hit(r.turn_index, r.syms[0].start, r.syms[-1].end, "NATIONAL_ID", PRIORITY_CUE, key) for r in chain]

    # ------------------------------------------------------ N-turn joins
    def _joins(self, view: ConversationView, runs: list[list[Run]], claimed: set) -> list[_Hit]:
        out: list[_Hit] = []
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
                found = self._classify(view, chain, cross_only=True, claimed=claimed)
                out.extend(found)
                if not found:
                    out.extend(self._partial_hetu(view, chain))
                if len(runs[j]) > 1 or runs[j][0].words_after > TAIL_SLACK:
                    break
        return out


def _classify_digits(d: str, plus: bool, ctx: list[str]) -> tuple[str, int] | None:
    n = len(d)
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
    if d.startswith("0") and 7 <= n <= 11 and not plus:
        return "PHONE", PRIORITY_VALIDATED
    account = _has_cue(ctx, ACCOUNT_CUES)
    if account and 6 <= n <= 12:
        return "ACCOUNT_NUMBER", PRIORITY_CUE
    if n in (8, 10) and not d.startswith("0") and _has_cue(ctx, NUMBER_CUES):
        return "ACCOUNT_NUMBER", PRIORITY_CUE
    if n == 16 and _has_cue(ctx, CARD_CUES):
        return "PAYMENT_CARD", PRIORITY_CUE
    if n == 4 and _has_cue(ctx, CARD_CUES):
        return "PAYMENT_CARD", PRIORITY_CUE
    if 4 <= n <= 8 and _has_cue(ctx, SECRET_CUES):
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
STRONG_SECRET_CUES = ("salasan", "password", "passw", "lösenord", "passphrase", "verkkoavain", "tunnuslause")
COPULAS = frozenset({"on", "oli", "is", "was", "är", "var", ":", "="})
HEDGES = frozenset({"varmaan", "kai", "luultavasti", "ehkä", "probably", "maybe", "still", "edelleen", "nog",
                    "kanske", "typ", "fortfarande", "nyt", "now", "nu"})
# Words that commonly follow "password is / salasana on / lösenordet är" as prose, not as the value
# (general-language list, not derived from the kit).
CREDENTIAL_PROSE = frozenset(["not", "no", "none", "never", "ei", "eikä", "inte", "icke", "wrong", "incorrect", "invalid", "expired", "changed", "correct", "right", "ok", "okay", "fine", "working", "broken", "locked", "blocked", "lost", "forgotten", "unknown", "new", "old", "same", "different", "too", "very", "still", "also", "just", "really", "väärä", "oikea", "vanha", "uusi", "sama", "eri", "liian", "tosi", "vielä", "edelleen", "myös", "vain", "hukassa", "lukossa", "voimassa", "vanhentunut", "vaihdettu", "unohtunut", "kadonnut", "estetty", "jotain", "mikä", "mitä", "tämä", "tuo", "sinun", "teidän", "minun", "hyvä", "huono", "pitkä", "lyhyt", "fel", "rätt", "gammal", "gamla", "ny", "nya", "samma", "annan", "för", "mycket", "fortfarande", "också", "bara", "glömt", "ändrat", "borta", "låst", "spärrat", "något", "vad", "detta", "det", "din", "ditt", "er", "bra", "dålig", "lång", "kort", "the", "a", "an", "my", "your", "this", "that", "what", "something", "required", "needed"])


def _alpha_credential(val: str) -> bool:
    """An alphabetic credential right after an explicit cue: one token of 4-32 characters that is not a
    common prose word and not a Finnish past participle ('vaihdettu', 'unohtunut')."""
    low = val.lower()
    if not (4 <= len(val) <= 32) or not re.fullmatch(r"[^\W\d_][\w!#$%&*+\-.@]*", val):
        return False
    if low in CREDENTIAL_PROSE or low in FILLER:
        return False
    return not re.search(r"(?:ttu|tty|nut|nyt|ttiin|tetty|tettu)$", low)


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
