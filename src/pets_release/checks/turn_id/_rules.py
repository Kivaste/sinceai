"""Rules of ``turn-id-synthetic`` (D21). Pure functions; no values ever leave.

A released ``turns.turn_id`` is a synthetic record key carrying no person or conversation
information iff all of these hold:

1. **Record key**: every value non-empty (``emptyKey``) and unique (``duplicateKey``).
2. **No conversation component** (``conversationComponent``): over the compact form (case-folded,
   alphanumerics only) no prefix or suffix of any length, and over the separator-split tokens no
   token position, is constant inside every multi-turn conversation while taking two or more
   values across them (a component that is a function of the conversation); and no original
   ``conversation_id`` (compact, >= ``CONV_MIN`` characters) occurs inside a value. Conversation
   grouping comes from the released ``turns.conversation_id`` (a release-scope pseudonym, which
   partitions rows exactly as the original). Fewer than two multi-turn conversations cannot show
   the absence of a component: ``undetermined`` (fail closed).
3. **No identifier value** (``identifierValue``): no value equals (compact, any length) an original
   value of a context ``identifiers`` column, and no such compact original of >= ``SUBSTRING_MIN``
   characters occurs inside a value (the same floors as ticket 11's original-value survival).
4. **No finer timestamp** (``sourceTimestamp``): the value's digits do not contain the minute-level
   prefix (``YYYYMMDDHHMM``) of any source ``turns.ts`` or ``conversations.started_ts``; the release
   carries timestamps at the hour only.

Source ``turns.turn_id`` is never used as an identifier here (it is the value under test).
"""
from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd

SUBSTRING_MIN = 8
CONV_MIN = 6
TS_DIGITS = 12
_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")
_TS_COLUMNS = (("turns", "ts"), ("conversations", "started_ts"))

LABELS = ("emptyKey", "duplicateKey", "conversationComponent", "undetermined", "identifierValue",
          "sourceTimestamp")


class RuleError(Exception):
    """Inputs malformed; the check raises, the runner records error. Content-free."""


def compact(v: str) -> str:
    return "".join(ch for ch in str(v).casefold() if ch.isalnum())


def _digits(v: str) -> str:
    return "".join(ch for ch in str(v) if ch.isdigit())


def _substrings(s: str, min_len: int) -> Iterable[str]:
    for i in range(len(s)):
        for j in range(i + min_len, len(s) + 1):
            yield s[i:j]


def _component_rows(ids: pd.Series, conv: pd.Series) -> tuple[set[int], bool]:
    """Row positions in multi-turn conversations if a conversation component exists; and whether
    the test was determinable (>= 2 multi-turn conversations)."""
    sizes = conv.map(conv.value_counts())
    multi = (sizes >= 2).to_numpy()
    if conv[multi].nunique() < 2:
        return set(), False
    cid = conv[multi].reset_index(drop=True)
    comp = ids[multi].map(compact).reset_index(drop=True)
    toks = ids[multi].map(lambda v: [t for t in _TOKEN_SPLIT.split(str(v).casefold()) if t]).reset_index(drop=True)
    width = int(comp.str.len().max() or 0)
    probes = []
    for n in range(1, width + 1):
        probes.append(comp.str[:n])
        probes.append(comp.str[-n:])
    depth = int(toks.map(len).max() or 0)
    for k in range(depth):
        probes.append(toks.map(lambda t, k=k: t[k] if k < len(t) else "\x00"))
    for p in probes:
        frame = pd.DataFrame({"c": cid, "p": p})
        if frame.groupby("c")["p"].nunique().max() == 1 and frame["p"].nunique() >= 2:
            return {i for i, m in enumerate(multi) if m}, True
    return set(), True


def evaluate(ids: pd.Series, conv: pd.Series, source: dict, identifiers: list) -> dict[str, set[int]]:
    """Map label -> set of 0-based row positions with a hit. ``ids``/``conv``: released columns."""
    ids = ids.reset_index(drop=True).astype(str)
    conv = conv.reset_index(drop=True).astype(str)
    if len(ids) != len(conv):
        raise RuleError("column length mismatch")
    hits: dict[str, set[int]] = {}

    empty = {i for i, v in enumerate(ids) if v.strip() == ""}
    if empty:
        hits["emptyKey"] = empty
    dup = ids.duplicated(keep=False) & (ids.str.strip() != "")
    if dup.any():
        hits["duplicateKey"] = set(dup[dup].index)

    comp_rows, determinable = _component_rows(ids, conv)
    if not determinable:
        hits["undetermined"] = set(range(len(ids)))

    try:
        s_turns, s_convs = source["turns"], source["conversations"]
        orig_conv = {compact(v) for v in s_convs["conversation_id"]} | {compact(v) for v in s_turns["conversation_id"]}
    except (KeyError, TypeError):
        raise RuleError("source turns/conversations missing") from None
    orig_conv = {c for c in orig_conv if len(c) >= CONV_MIN}

    whole: set[str] = set()
    long_: set[str] = set()
    for spec in identifiers:
        t, c = spec["table"], spec["column"]
        if (t, c) == ("turns", "turn_id"):
            continue
        try:
            col = source[t][c]
        except (KeyError, TypeError):
            raise RuleError("identifier column missing from source") from None
        for v in col.dropna():
            cv = compact(v)
            if cv:
                whole.add(cv)
                if len(cv) >= SUBSTRING_MIN:
                    long_.add(cv)

    ts_set: set[str] = set()
    for t, c in _TS_COLUMNS:
        try:
            col = source[t][c]
        except (KeyError, TypeError):
            raise RuleError("source timestamp column missing") from None
        for v in col.dropna():
            d = _digits(v)
            if len(d) >= TS_DIGITS:
                ts_set.add(d[:TS_DIGITS])

    conv_hit, ident_hit, ts_hit = set(), set(), set()
    for i, v in enumerate(ids):
        cv = compact(v)
        if not cv:
            continue
        subs = set(_substrings(cv, min(CONV_MIN, SUBSTRING_MIN)))
        if subs & orig_conv:
            conv_hit.add(i)
        if cv in whole or subs & long_:
            ident_hit.add(i)
        d = _digits(v)
        if ts_set and any(d[j:j + TS_DIGITS] in ts_set for j in range(len(d) - TS_DIGITS + 1)):
            ts_hit.add(i)
    if comp_rows or conv_hit:
        hits["conversationComponent"] = comp_rows | conv_hit
    if ident_hit:
        hits["identifierValue"] = ident_hit
    if ts_hit:
        hits["sourceTimestamp"] = ts_hit
    return hits
