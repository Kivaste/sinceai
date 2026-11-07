"""Fuzzy quasi-identifier matching of one adversary record against a protected table.

Own implementation (not the kit's). A protected cell that is blank or masked is a
wildcard: the attacker learns nothing from it and cannot rule the row out.
No truth is read here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

REF = pd.Timestamp("2025-12-31")
_SEP = re.compile(r"[\s\-\.\(\)/_:]+")
_MASKED = re.compile(r"^[\*x#?\-_]*$", re.IGNORECASE)
_SEX = {"m": "M", "male": "M", "mies": "M", "man": "M", "f": "F", "female": "F", "nainen": "F",
        "woman": "F", "kvinna": "F", "n": "F", "k": "F"}


@dataclass
class QI:
    kind: str  # exact | name | postcode | age | sex | time
    adv: tuple
    prot: tuple
    window: tuple | None = None  # time: (hours before, hours after) adversary time
    tol: float | None = None  # age: years


def qis_from_spec(spec: list, columns) -> list:
    """QIs from kit-style spec dicts, dropping those whose protected columns are absent."""
    cols = set(columns)
    out = []
    for q in spec:
        prot = tuple(c for c in q["protected"] if c in cols)
        if prot and q["kind"] in ("exact", "name", "postcode", "age", "sex", "time"):
            out.append(QI(q["kind"], tuple(q["adversary"]), prot,
                          tuple(q["window"]) if q.get("window") else None, q.get("tol")))
    return out


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "" or bool(_MASKED.match(str(v).strip()))


def _norm(v) -> str:
    return "" if _blank(v) else _SEP.sub("", str(v).lower().strip())


def edit_le1(a: str, b: str) -> bool:
    """True when the Levenshtein distance is at most one."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


def _tokens(s) -> set:
    t = re.sub(r"[^\w\s\-]", " ", str(s).lower())
    return {x for x in re.split(r"[\s\-]+", t) if len(x) >= 2}


def parse_interval(s: pd.Series):
    """[start, end) per cell for datetimes, dates, months, years and ISO weeks. NaT when unusable."""
    start = np.full(len(s), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    end = start.copy()
    cache: dict = {}
    for i, raw in enumerate(s.fillna("").astype(str).str.strip().tolist()):
        if raw not in cache:
            cache[raw] = _interval_one(raw)
        a, b = cache[raw]
        if a is not None:
            start[i], end[i] = a, b
    return start, end


def _interval_one(raw: str):
    try:
        if re.fullmatch(r"\d{4}", raw):
            a = pd.Timestamp(int(raw), 1, 1)
            return a.to_datetime64(), (a + pd.DateOffset(years=1)).to_datetime64()
        if re.fullmatch(r"\d{4}-\d{2}", raw):
            a = pd.Timestamp(raw + "-01")
            return a.to_datetime64(), (a + pd.DateOffset(months=1)).to_datetime64()
        m = re.fullmatch(r"(\d{4})-?W(\d{1,2})", raw)
        if m:
            a = pd.Timestamp.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
            return a.to_datetime64(), (a + pd.Timedelta(days=7)).to_datetime64()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            a = pd.Timestamp(raw)
            return a.to_datetime64(), (a + pd.Timedelta(days=1)).to_datetime64()
        if re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}", raw):
            a = pd.Timestamp(raw)
            if a.tzinfo is not None:
                a = a.tz_convert("UTC").tz_localize(None)
            return a.to_datetime64(), a.to_datetime64()
    except (ValueError, TypeError):
        pass
    return None, None


def _age_interval(s: pd.Series, col: str):
    """Age-in-years interval [lo, hi) at REF per protected cell from a birth date/year, age or band."""
    n = len(s)
    lo, hi = np.full(n, -1.0), np.full(n, 200.0)  # wildcard
    birth = "birth" in col.lower() or "dob" in col.lower()
    cache: dict = {}
    for i, raw in enumerate(s.fillna("").astype(str).str.strip().tolist()):
        if raw not in cache:
            cache[raw] = _age_one(raw, birth)
        if cache[raw] is not None:
            lo[i], hi[i] = cache[raw]
    return lo, hi


def _age_one(raw: str, birth: bool):
    if raw == "" or _MASKED.match(raw):
        return None
    if birth:
        a, b = _interval_one(raw)
        if a is None:
            return None
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        return (REF - b).days / 365.25, (REF - a).days / 365.25 + 1e-9
    m = re.fullmatch(r"[\[(]?\s*(\d+)\s*(?:-|â€“|,|\.\.)\s*(\d+)\s*[\])]?", raw)
    if m:
        return float(m.group(1)), float(m.group(2)) + 1
    m = re.fullmatch(r"(\d+)\s*\+", raw)
    if m:
        return float(m.group(1)), 130.0
    m = re.fullmatch(r"<\s*(\d+)", raw)
    if m:
        return 0.0, float(m.group(1))
    try:
        a = float(raw.replace(",", "."))
        return a, a + 1
    except ValueError:
        return None


class Matcher:
    """Index a protected table once; ask for the candidate rows of each adversary record."""

    def __init__(self, protected: pd.DataFrame, qis: list):
        self.n = len(protected)
        self.qis = qis
        self.d: dict = {}
        for i, q in enumerate(qis):
            col = protected[q.prot[0]]
            if q.kind == "exact":
                self.d[i] = np.array([_norm(v) for v in col.tolist()], dtype=object)
            elif q.kind == "sex":
                self.d[i] = np.array(["" if _blank(v) else _SEX.get(str(v).strip().lower(), "") for v in col.tolist()], dtype=object)
            elif q.kind == "postcode":
                self.d[i] = np.array([re.sub(r"\D", "", "" if _blank(v) else str(v)) for v in col.tolist()], dtype=object)
            elif q.kind == "age":
                self.d[i] = _age_interval(col, q.prot[0])
            elif q.kind == "time":
                self.d[i] = parse_interval(col)
            elif q.kind == "name":
                full = protected[list(q.prot)].fillna("").astype(str).agg(" ".join, axis=1).tolist()
                index: dict = {}
                has = np.zeros(self.n, bool)
                for r, text in enumerate(full):
                    ts = _tokens(text)
                    has[r] = bool(ts)
                    for t in ts:
                        index.setdefault(t, []).append(r)
                self.d[i] = (index, has, {})

    def _name_mask(self, i: int, text) -> np.ndarray | None:
        at = _tokens(text)
        if not at:
            return None
        index, has, cache = self.d[i]
        mask = np.ones(self.n, bool)
        for t in at:
            if t not in cache:
                rows = [r for tok, rs in index.items() if edit_le1(t, tok) for r in rs]
                m = np.zeros(self.n, bool)
                m[rows] = True
                cache[t] = m
            mask &= cache[t]
        return mask | ~has

    def candidates(self, row: dict):
        mask = np.ones(self.n, bool)
        used = 0
        for i, q in enumerate(self.qis):
            if q.kind == "name":
                m = self._name_mask(i, " ".join(str(row.get(c, "")) for c in q.adv if not _blank(row.get(c))))
                if m is None:
                    continue
                mask &= m
            elif q.kind in ("exact", "sex"):
                v = row.get(q.adv[0])
                a = _norm(v) if q.kind == "exact" else ("" if _blank(v) else _SEX.get(str(v).strip().lower(), ""))
                if not a:
                    continue
                mask &= (self.d[i] == a) | (self.d[i] == "")
            elif q.kind == "postcode":
                v = row.get(q.adv[0])
                a = re.sub(r"\D", "", "" if _blank(v) else str(v))
                if not a:
                    continue
                mask &= np.fromiter((p == "" or a.startswith(p) or p.startswith(a) for p in self.d[i]), bool, self.n)
            elif q.kind == "age":
                v = next((row.get(c) for c in q.adv if not _blank(row.get(c))), None)
                if v is None:
                    continue
                try:
                    a = float(str(v).replace(",", "."))
                except ValueError:
                    continue
                tol = 1.0 if q.tol is None else q.tol
                lo, hi = self.d[i]
                mask &= (lo < a + 1 + tol) & (hi > a - tol)
            elif q.kind == "time":
                parts = [str(row.get(c)).strip() for c in q.adv if not _blank(row.get(c))]
                if not parts:
                    continue
                v = parts[0]
                if len(parts) > 1 and re.fullmatch(r"\d{1,2}[:.]\d{2}(:\d{2})?", parts[1]):
                    v = parts[0] + " " + parts[1].replace(".", ":")
                a, b = _interval_one(v)
                if a is None:
                    continue
                t0, t1 = pd.Timestamp(a), pd.Timestamp(b)
                before, after = q.window if q.window else (24, 24)
                a0 = (t0 - pd.Timedelta(hours=before)).to_datetime64()
                a1 = (t1 + pd.Timedelta(hours=after) - (pd.Timedelta(1, 'ns') if t1 > t0 else pd.Timedelta(0))).to_datetime64()
                s, e = self.d[i]
                known = ~np.isnat(s)
                ok = np.ones(self.n, bool)
                ok[known] = (s[known] <= a1) & (np.maximum(e[known], s[known]) >= a0)
                mask &= ok
            used += 1
        return np.flatnonzero(mask), used


