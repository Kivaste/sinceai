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


KINDS = ("exact", "name", "postcode", "age", "sex", "time")


@dataclass
class QI:
    kind: str  # exact | name | postcode | age | sex | time
    adv: tuple
    prot: tuple
    window: tuple | None = None  # time: (hours before, hours after) adversary time
    tol: float | None = None  # age: years


def qis_from_spec(spec: list, columns) -> list:
    """QIs from kit-style spec dicts, dropping those whose protected columns are absent.
    An unknown kind is an error (never silently skipped: that would understate the risk)."""
    cols = set(columns)
    out = []
    for q in spec:
        if q["kind"] not in KINDS:
            raise ValueError(f"unknown QI kind {q['kind']!r}")
        prot = tuple(c for c in q["protected"] if c in cols)
        if prot:
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


class RungError(ValueError):
    """Rung metadata missing, unknown, or contradicted by the released cells. Scoring refused."""


# Anchored cell forms per rung (ticket 07 contract forms; kit-baseline forms allowed where noted).
_TIME_FORMS = {
    "ts.exact": r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?",
    "ts.hour": r"\d{4}-\d{2}-\d{2}[T ]\d{2}:00",
    "ts.month_hour": r"\d{4}-\d{2}-01T\d{2}:00",
    "ts.hour_of_day": r"(?:[01]\d|2[0-3]):00",
    "ts.day": r"\d{4}-\d{2}-\d{2}",
    "ts.week": r"\d{4}-W\d{2}",
    "ts.month": r"\d{4}-\d{2}",
}
_AGE_FORMS = {
    "age.band5": r"(?:\d{1,2}-\d{1,2}|90\+)",
    "age.band10": r"(?:\d{1,2}-\d{1,2}|90\+)",
    "age.years": r"\d{1,3}",
    "dob.date": r"\d{4}-\d{2}-\d{2}",
    "dob.month": r"\d{4}-\d{2}",
    "dob.year": r"\d{4}",
}
_EXACT_RUNGS = frozenset({"keep", "geo.full", "geo.topn"})
WITHHELD = "withheld"
KIND_RUNGS = {"time": set(_TIME_FORMS), "age": set(_AGE_FORMS), "exact": set(_EXACT_RUNGS),
              "name": {"keep", "text.redacted"}, "sex": {"keep"}, "postcode": {"keep", "geo.full", "geo.topn"}}
AGE_MAX = 130.0


def _need_rung(rungs: dict, col: str, kind: str) -> str:
    r = rungs.get(col) if rungs else None
    if r is None:
        raise RungError(f"no rung metadata for column {col!r}")
    if r != WITHHELD and r not in KIND_RUNGS[kind]:
        raise RungError(f"rung {r!r} is not valid for a {kind} column ({col!r})")
    return r


def _cells(s: pd.Series) -> list:
    return ["" if _blank(v) else str(v).strip() for v in s.tolist()]


def parse_interval(s: pd.Series, rung: str):
    """[start, end) per cell, read by the DECLARED rung (never by cell shape). NaT for blank cells.
    A non-blank cell that does not fit the rung's form is a RungError."""
    start = np.full(len(s), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    end = start.copy()
    if rung == WITHHELD:
        return start, end
    form = _TIME_FORMS.get(rung)
    if form is None:
        raise RungError(f"unknown timestamp rung {rung!r}")
    if rung in ("ts.month_hour", "ts.hour_of_day"):  # no instant to place; matched by key
        for raw in _cells(s):
            if raw and not re.fullmatch(form, raw):
                raise RungError("cell does not fit its declared rung")
            m = _MONTH_HOUR.fullmatch(raw) if raw and rung == "ts.month_hour" else None
            if m and not (1 <= int(m.group(2)) <= 12 and int(m.group(3)) <= 23):
                raise RungError("cell does not fit its declared rung")
        return start, end
    cache: dict = {}
    for i, raw in enumerate(_cells(s)):
        if raw == "":
            continue
        if raw not in cache:
            if not re.fullmatch(form, raw):
                raise RungError("cell does not fit its declared rung")
            cache[raw] = _interval_one(raw)
        a, b = cache[raw]
        if a is None:
            raise RungError("cell does not fit its declared rung")
        start[i], end[i] = a, b
    if rung == "ts.hour":
        end = np.where(np.isnat(start), end, start + np.timedelta64(1, "h"))
    elif rung == "ts.exact":
        end = start.copy()
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


def _age_interval(s: pd.Series, rung: str):
    """Age-in-years interval [lo, hi) at REF per cell, read by the declared rung. Blank cell = wildcard."""
    n = len(s)
    lo, hi = np.full(n, -1.0), np.full(n, 200.0)
    if rung == WITHHELD:
        return lo, hi
    form = _AGE_FORMS[rung]
    cache: dict = {}
    for i, raw in enumerate(_cells(s)):
        if raw == "":
            continue
        if raw not in cache:
            if not re.fullmatch(form, raw):
                raise RungError("cell does not fit its declared rung")
            cache[raw] = _age_one(raw, rung)
        lo[i], hi[i] = cache[raw]
    return lo, hi


def _age_one(raw: str, rung: str):
    if rung.startswith("dob."):
        a, b = _interval_one(raw)
        if a is None or b is None:  # fits the form but is not a real date (e.g. day 30 of February)
            raise RungError("cell does not fit its declared rung")
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        return (REF - b).days / 365.25, (REF - a).days / 365.25 + 1e-9
    if rung == "age.years":
        return float(raw), float(raw) + 1
    m = re.fullmatch(r"(\d+)-(\d+)", raw)
    if m:
        if int(m.group(1)) > int(m.group(2)):  # inverted band
            raise RungError("cell does not fit its declared rung")
        return float(m.group(1)), float(m.group(2)) + 1
    return float(raw[:-1]), 130.0  # "90+"


_MONTH_HOUR = re.compile(r"(\d{4})-(\d{2})-01T(\d{2}):00")


def _month_hour_keys(col: pd.Series) -> np.ndarray:
    """year*10^4+month*10^2+hour for ts.month_hour cells (YYYY-MM-01THH:00), else -1."""
    out = np.full(len(col), -1, dtype=np.int64)
    for i, raw in enumerate(col.fillna("").astype(str).str.strip().tolist()):
        m = _MONTH_HOUR.fullmatch(raw)
        if m:
            out[i] = int(m.group(1)) * 10_000 + int(m.group(2)) * 100 + int(m.group(3))
    return out


def _hod_keys(col: pd.Series) -> np.ndarray:
    """Hour of day for ts.hour_of_day cells (HH:00), else -1 (blank = wildcard)."""
    out = np.full(len(col), -1, dtype=np.int64)
    for i, raw in enumerate(col.fillna("").astype(str).str.strip().tolist()):
        if raw:
            out[i] = int(raw[:2])
    return out


def _hour_keys(a0, a1) -> np.ndarray:
    hours = pd.date_range(pd.Timestamp(a0).floor("h"), pd.Timestamp(a1), freq="h")
    return (hours.year * 10_000 + hours.month * 100 + hours.hour).to_numpy(dtype=np.int64)


class Matcher:
    """Index a protected table once; ask for the candidate rows of each adversary record."""

    def __init__(self, protected: pd.DataFrame, qis: list, rungs: dict):
        self.n = len(protected)
        self.qis = qis
        self.d: dict = {}
        self.inf: dict = {}  # QI index -> protected column has a non-wildcard cell
        for i, q in enumerate(qis):
            col = protected[q.prot[0]]
            if q.kind in ("name", "sex", "postcode"):
                for c in q.prot:
                    _need_rung(rungs, c, q.kind)
            if q.kind == "exact":
                vals = np.array([_norm(v) for v in col.tolist()], dtype=object)
                rung = _need_rung(rungs, q.prot[0], "exact")
                # only geo.topn groups the tail into "other"; elsewhere "other" is a literal place
                known = set(vals) - {"", "other"} if rung == "geo.topn" else None
                self.d[i] = (vals, known)
                self.inf[i] = bool((vals != "").any())
            elif q.kind == "sex":
                self.d[i] = np.array(["" if _blank(v) else _SEX.get(str(v).strip().lower(), "") for v in col.tolist()], dtype=object)
                self.inf[i] = bool((self.d[i] != "").any())
            elif q.kind == "postcode":
                self.d[i] = np.array([re.sub(r"\D", "", "" if _blank(v) else str(v)) for v in col.tolist()], dtype=object)
                self.inf[i] = bool((self.d[i] != "").any())
            elif q.kind == "age":
                self.d[i] = _age_interval(col, _need_rung(rungs, q.prot[0], "age"))
                self.inf[i] = bool((self.d[i][0] > -1.0).any())
            elif q.kind == "time":
                rung = _need_rung(rungs, q.prot[0], "time")
                mh = _month_hour_keys(col) if rung == "ts.month_hour" else np.full(self.n, -1, dtype=np.int64)
                hod = _hod_keys(col) if rung == "ts.hour_of_day" else np.full(self.n, -1, dtype=np.int64)
                self.d[i] = parse_interval(col, rung) + (mh, hod)
                self.inf[i] = bool((~np.isnat(self.d[i][0])).any() or (mh >= 0).any() or (hod >= 0).any())
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
                self.inf[i] = bool(has.any())

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
                if q.kind == "exact":
                    vals, known = self.d[i]
                    ok = (vals == a) | (vals == "")
                    if known is not None:
                        ok |= (vals == "other") & (a not in known)
                else:
                    ok = (self.d[i] == a) | (self.d[i] == "")
                mask &= ok
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
                    raise RungError("adversary age value does not parse as an age") from None
                if not (0 <= a <= AGE_MAX):
                    raise RungError("adversary age value outside a plausible age range")
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
                    raise RungError("adversary time value does not parse")
                t0, t1 = pd.Timestamp(a), pd.Timestamp(b)
                before, after = q.window if q.window else (24, 24)
                a0 = (t0 - pd.Timedelta(hours=before)).to_datetime64()
                a1 = (t1 + pd.Timedelta(hours=after) - (pd.Timedelta(1, 'ns') if t1 > t0 else pd.Timedelta(0))).to_datetime64()
                s, e, mh, hod = self.d[i]
                known = ~np.isnat(s) & (mh < 0)
                ok = np.ones(self.n, bool)
                sk, ek = s[known], e[known]
                # buckets are half-open [s, e); an exact instant (e == s) matches at both window edges
                ok[known] = (sk <= a1) & ((ek > a0) | ((ek == sk) & (sk >= a0)))
                is_mh = mh >= 0
                if is_mh.any():
                    ok[is_mh] = np.isin(mh[is_mh], _hour_keys(a0, a1))
                is_hod = hod >= 0
                if is_hod.any():  # hour of day only, any date; blank cells stay compatible
                    hrs = pd.date_range(pd.Timestamp(a0).floor("h"), pd.Timestamp(a1), freq="h").hour
                    ok[is_hod] = np.isin(hod[is_hod], np.unique(hrs))
                mask &= ok
            if self.inf[i]:
                used += 1
        return np.flatnonzero(mask), used





