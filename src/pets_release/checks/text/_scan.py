"""Find declared text fields in a release and scan them per conversation.

Text fields are the contract columns whose form is the validator ID ``text``. A
conversational field names its conversation column and its order column in ``params``:
``{"form": "text", "params": {"conversation": "conversation_id", "order": "seq"}}``; its rows
are grouped and stitched per conversation. A text field with neither param (free notes) is
scanned row by row. Naming only one of the two is an error.
"""
from __future__ import annotations

import json
import weakref

from . import _normalise as normalise

TEXT_FORM = "text"
# A column with a non-text form is treated as undeclared free text (and the text checks
# error) if at least this share of its non-empty values has at least this many tokens.
UNDECLARED_TEXT_TOKENS = 6
UNDECLARED_TEXT_SHARE = 0.2


class TextCheckError(Exception):
    """The text checks cannot run on this release/contract; the runner records `error`."""


def text_fields(contract):
    """[(file, column, conversation_col, order_col)] sorted; raises on malformed declarations."""
    files = contract.get("files") if isinstance(contract, dict) else None
    if not isinstance(files, dict):
        raise TextCheckError("contract has no files mapping")
    out = []
    for fname in sorted(files):
        cols = (files[fname] or {}).get("columns", {})
        if not isinstance(cols, dict):
            raise TextCheckError("contract columns malformed")
        for col in sorted(cols):
            spec = cols[col] or {}
            if spec.get("form") != TEXT_FORM:
                continue
            params = spec.get("params") or {}
            conv, order = params.get("conversation"), params.get("order")
            if conv is None and order is None:
                pass  # not conversational: each row is its own conversation
            elif not isinstance(conv, str) or not isinstance(order, str):
                raise TextCheckError("text column names only one of conversation/order")
            out.append((fname, col, conv, order))
    return out


class Conversation:
    """Source turns of one conversation (in order) plus cached normalised views.

    ``views[kind]`` holds one view per turn; ``windows[kind]`` holds (idx, joined view, bounds)
    for every N-turn window, computed from the joined *source* turns.
    """

    __slots__ = ("rows", "src", "views", "_windows")

    def __init__(self):
        self.rows, self.src = [], []
        self.views = {"digit": [], "email": []}
        self._windows = {}

    def windows(self, kind):
        if kind not in self._windows:
            digit = self.views["digit"]
            out = []
            for idx in normalise.windows(len(self.src), lambda i: any(ch.isdigit() for ch in digit[i])):
                joined, bounds = normalise.join(self.src, idx)
                out.append((idx, joined, normalise.view(joined, kind), bounds))
            self._windows[kind] = out
        return self._windows[kind]


class TextField:
    def __init__(self, fname, column, conversations, n_turns):
        self.file = fname
        self.column = column
        self.conversations = conversations
        self.n_turns = n_turns


# Per Release object (one gate/verify run), per canonical contract: the normalised views.
_CACHE: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _column(table, name):
    idx = [i for i, h in enumerate(table.header) if h == name]
    if len(idx) != 1:
        raise TextCheckError("declared column missing or duplicated in release file")
    return [str(v) for v in table.frame.iloc[:, idx[0]].tolist()]


def load(release, contract):
    """Return [TextField] for the declared text fields of this release."""
    key = json.dumps(contract, sort_keys=True, separators=(",", ":"), default=str)
    try:
        per_release = _CACHE.setdefault(release, {})
    except TypeError:
        per_release = {}
    if key in per_release:
        return per_release[key]

    fields = text_fields(contract)
    files = contract["files"]
    declared = {(f, c) for f, c, _, _ in fields}
    result = []
    for fname in sorted(files):
        if fname not in release.csv_files:
            raise TextCheckError("contract file missing from release")
        table = release.table(fname)
        for col in table.header:
            if (fname, col) in declared:
                continue
            vals = [v for v in _column(table, col) if v.strip()]
            if vals:
                wordy = sum(1 for v in vals if len(v.split()) >= UNDECLARED_TEXT_TOKENS)
                if wordy / len(vals) >= UNDECLARED_TEXT_SHARE:
                    raise TextCheckError("undeclared free-text column in release")
        for f, col, conv, order in fields:
            if f != fname:
                continue
            texts = _column(table, col)
            if conv is None:
                convs_col = [str(i) for i in range(len(texts))]
                orders = ["0"] * len(texts)
            else:
                convs_col, orders = _column(table, conv), _column(table, order)

            def order_key(r_i, orders=orders):
                v = orders[r_i]
                return (0, int(v), "", r_i) if v.isdigit() else (1, 0, v, r_i)

            groups = {}
            for r_i, cid in enumerate(convs_col):
                groups.setdefault(cid, []).append(r_i)
            convs = []
            for cid in sorted(groups, key=lambda k: groups[k][0]):
                c = Conversation()
                for r_i in sorted(groups[cid], key=order_key):
                    text = texts[r_i]
                    c.rows.append(r_i)
                    c.src.append(text)
                    c.views["digit"].append(normalise.view(text, "digit"))
                    c.views["email"].append(normalise.view(text, "email"))
                convs.append(c)
            result.append(TextField(fname, col, convs, len(texts)))
    per_release[key] = result
    return result


def _source_parts(src_text, kind, s, e, bounds):
    """Map a hit [s, e) in view(src_text) to [(turn, start, end)] in source-turn offsets."""
    _out, starts, ends = normalise.view(src_text, kind, with_map=True)
    a, b = normalise.source_span(starts, ends, s, e)
    parts = []
    for bs, be, t in bounds:
        lo, hi = max(a, bs), min(b, be)
        if lo < hi:
            parts.append((t, lo - bs, hi - bs))
    return parts


def _ov(a, b):
    return a[0] == b[0] and a[1] < b[2] and b[1] < a[2]


def _within(inner, outer_parts):
    return any(inner[0] == o[0] and o[1] <= inner[1] and inner[2] <= o[2] for o in outer_parts)


def _add(found, parts):
    """Add a hit (list of (turn, start, end) source parts) unless it overlaps an existing one.

    A hit that fully contains every hit it overlaps replaces them (a window hit extends a
    fragment already found in one turn); any other overlap is the same identifier, dropped.
    """
    clash = [h for h in found if any(_ov(a, b) for a in h for b in parts)]
    if clash and not all(_within(a, parts) for h in clash for a in h):
        return
    for h in clash:
        found.remove(h)
    found.append(parts)


def detect(field: TextField, detector, view: str):
    """Run one detector over single turns, then over 2- and 3-turn windows.

    Windows are normalised from the joined source turns. Returns a list of hits, each a
    sorted tuple of row indices the hit touches. A window hit counts only if it spans the
    first and last turn of the window; overlapping hits are merged (see ``_add``).
    """
    hits = []
    for conv in field.conversations:
        found: list = []
        for t, text in enumerate(conv.views[view]):
            src = conv.src[t]
            for s, e in detector(text):
                parts = _source_parts(src, view, s, e, [(0, len(src), t)])
                if parts:
                    _add(found, parts)
        if len(conv.src) > 1:
            for idx, joined_src, joined_view, bounds in conv.windows(view):
                for s, e in detector(joined_view):
                    parts = _source_parts(joined_src, view, s, e, bounds)
                    touched = {p[0] for p in parts}
                    if idx[0] in touched and idx[-1] in touched:
                        _add(found, parts)
        for parts in found:
            hits.append(tuple(sorted({conv.rows[t] for t, _s, _e in parts})))
    return hits
