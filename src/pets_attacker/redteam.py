"""Red team (#139): an attacker stronger than the spec-driven broker persona. Measure-only; aggregates only.

cross_dataset        each adversary record is enriched from the kit's other-domain person tables (and the sports
                     rosters adversary file), joined on the full name (and the place when the record states one):
                     an unambiguous birth date gives an age at the event, plus sex and place when unambiguous.
                     Worst case: those tables count as attacker knowledge. Then scored as range_aware.
range_aware          Fellegi-Sunter scoring of interval overlaps: per stated field, the share u of released rows
                     compatible with the stated value; a compatible row gains log(M/u), an incompatible one
                     log((1-M)/(1-u)). A disagreeing field lowers a row's score instead of vetoing it (the hard
                     filter of the personas). Reports the unique re-identification rate (a single best row of the
                     right person) and the 1-in-k guess success (expected success of guessing among the best rows).
attribute_inference  per released sensitive attribute (field-catalog role), an attacker who knows a released
                     visit's exact QIs predicts the most common value among the best-scoring rows; compared with
                     the base rate (always guessing the release's most common value) on the same targets.

Truth arrives as DataFrames; this module reads only the kit's public data and adversary folders. A failure gives an
attack ``evaluated: false`` with a reason code from REASONS, never a rate.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .linkage import _SEX, AGE_MAX, REF, _blank, _interval_one, _norm, _tokens, qis_from_spec
from .linkage import Matcher
from .personas import MAX_SAMPLE, SEED, _World

M = 0.95  # Fellegi-Sunter m: probability that a true match agrees on a stated field
TIE = 1e-9

# (file under the kit root, name columns, birth column, birth is a year, place column, sex column)
AUX_SOURCES = (
    ("data/finance/customers.csv", ("full_name",), "birth_date", False, "city", None),
    ("data/energy/customers.csv", ("customer_name",), "birth_date", False, "municipality", None),
    ("data/education/students.csv", ("first_names", "last_name"), "birth_date", False, "municipality", "sex"),
    ("data/mobility/cards.csv", ("holder_name",), "holder_birth_date", False, None, None),
    ("data/customer_service/customers.csv", ("full_name",), None, False, "city", None),
    ("data/public_admin/building_permits.csv", ("applicant_name",), None, False, "municipality", None),
    ("adversary/sports_club_rosters.csv", ("player_name",), "birth_year", True, "home_town", None),
)
AGE_COLS = ["date_of_birth", "age", "age_band"]
REASONS = frozenset({"no-aux-table", "aux-table-malformed", "no-field-catalog", "no-sensitive-released",
                     "no-target", "no-attack-spec", "no-link-to-target-table", "no-register"})
LINK_KEYS = ("evaluated", "reason", "n_targets", "n_unique_claims", "reidentification_rate", "guess_rate",
             "median_top_set", "n_enriched", "n_aux_sources")
ATTR_KEYS = ("evaluated", "reason", "n_targets", "inference_rate", "baseline_rate")


class RedTeamError(ValueError):
    """An attack cannot run; ``code`` is one of REASONS."""

    def __init__(self, code: str):
        assert code in REASONS
        super().__init__(code)
        self.code = code


def failed(e: Exception, keys=LINK_KEYS) -> dict:
    out = {k: None for k in keys}
    out.update(evaluated=False, reason=e.code if isinstance(e, RedTeamError) else f"error:{type(e).__name__}")
    return out


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def fs_top(matcher: Matcher, row: dict):
    """Best-scoring released rows for ``row`` and the number of fields that ranked rows."""
    score = np.zeros(matcher.n)
    used = 0
    for i, mask in matcher.qi_masks(row):
        if not matcher.inf[i]:
            continue
        u = float(mask.mean())
        if u <= 0.0 or u >= 1.0:  # no row or every row agrees: the field does not rank rows
            continue
        score += np.where(mask, np.log(M / u), np.log((1 - M) / (1 - u)))
        used += 1
    if used == 0:
        return np.arange(matcher.n), 0
    return np.flatnonzero(score >= score.max() - TIE), used


class _AuxIndex:
    """Full-name tokens -> [(birth date or None, place, sex)] over the auxiliary tables present in the kit."""

    def __init__(self, kit: Path):
        self.index: dict = {}
        self.n_sources = 0
        for rel, names, birth, year_only, place, sex in AUX_SOURCES:
            p = Path(kit) / rel
            if not p.is_file():
                continue
            df = _read(p)
            need = [c for c in (*names, birth, place, sex) if c]
            if not set(need) <= set(df.columns):
                raise RedTeamError("aux-table-malformed")
            self.n_sources += 1
            text = df[list(names)].agg(" ".join, axis=1).tolist()
            births = df[birth].tolist() if birth else [""] * len(df)
            places = df[place].tolist() if place else [""] * len(df)
            sexes = df[sex].tolist() if sex else [""] * len(df)
            for t, b, pl, sx in zip(text, births, places, sexes):
                key = frozenset(_tokens(t))
                if len(key) < 2:
                    continue
                self.index.setdefault(key, []).append((_birth(b, year_only), _norm(pl),
                                                       _SEX.get(str(sx).strip().lower(), "")))

    def enrich(self, name: str, place: str):
        """(birth date, sex, place) the auxiliary tables agree on for this full name; None where ambiguous."""
        key = frozenset(_tokens(name))
        if len(key) < 2:
            return None, None, None
        hits = [h for h in self.index.get(key, ()) if not place or not h[1] or h[1] == place]
        births = {h[0] for h in hits if h[0] is not None}
        sexes = {h[2] for h in hits if h[2]}
        places = {h[1] for h in hits if h[1]}
        one = lambda s: next(iter(s)) if len(s) == 1 else None  # noqa: E731
        return one(births), one(sexes), one(places)


def _birth(raw, year_only: bool):
    raw = str(raw).strip()
    if _blank(raw):
        return None
    try:
        ts = pd.Timestamp(f"{int(raw)}-07-01") if year_only else pd.Timestamp(raw[:10])
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts


def _age_at(birth, when) -> float | None:
    a = (when - birth).days / 365.25
    return a if 0.0 <= a <= AGE_MAX else None


def _first(row: dict, cols) -> str:
    return next((str(row.get(c)).strip() for c in cols if not _blank(row.get(c))), "")


def _event_time(row: dict, spec_qis: list):
    for q in spec_qis:
        if q["kind"] == "time":
            v = _first(row, q["adversary"])
            a, _ = _interval_one(v) if v else (None, None)
            if a is not None:
                return pd.Timestamp(a)
    return REF


def _cols(spec_qis: list, kind: str) -> list:
    return [c for q in spec_qis if q["kind"] == kind for c in q["adversary"]]


EXTRA_QIS = [{"kind": "age", "adversary": ["_x_age"], "protected": AGE_COLS, "tol": 1},
             {"kind": "sex", "adversary": ["_x_sex"], "protected": ["sex"]},
             {"kind": "exact", "adversary": ["_x_place"], "protected": ["municipality"]}]


def linkage(kit: Path, specs: list, world: _World, protected: pd.DataFrame, rungs: dict, adv_frames: dict,
            adv_truths: dict, *, enrich: bool) -> dict:
    """Pooled over the scenario's adversary sources: unique re-identification and 1-in-k guess success."""
    aux = _AuxIndex(kit) if enrich else None
    if aux is not None and aux.n_sources == 0:
        raise RedTeamError("no-aux-table")
    if not specs:
        raise RedTeamError("no-attack-spec")
    prot = protected.reset_index(drop=True)
    n = claims = correct = enriched = 0
    guess = 0.0
    sizes: list = []
    for spec in specs:
        adv = adv_frames[spec["adversary"]].reset_index(drop=True)
        tmap = dict(zip(adv_truths[spec["adversary"]].iloc[:, 0].astype(str),
                        adv_truths[spec["adversary"]].iloc[:, 1].astype(str)))
        if len(adv) > MAX_SAMPLE:  # the broker persona's frame: same seed, same cap
            adv = adv.iloc[np.sort(np.random.default_rng(SEED).choice(len(adv), MAX_SAMPLE, replace=False))]
        qspec = list(spec["qis"]) + (EXTRA_QIS if enrich else [])
        matcher = Matcher(prot, qis_from_spec(qspec, prot.columns), rungs)
        for r in adv.to_dict("records"):
            pid = tmap.get(str(r[adv.columns[0]]), "")
            if pid not in world.persons:
                continue
            n += 1
            if enrich:
                place = _norm(_first(r, _cols(spec["qis"], "exact")))
                birth, sex, aux_place = aux.enrich(" ".join(_first(r, [c]) for c in _cols(spec["qis"], "name")),
                                                   place)
                age = _age_at(birth, _event_time(r, spec["qis"])) if birth is not None else None
                r = dict(r, _x_age="" if age is None else f"{age:.4f}", _x_sex=sex or "",
                         _x_place="" if place or not aux_place else aux_place)
                enriched += bool(r["_x_age"] or r["_x_sex"] or r["_x_place"])
            top, used = fs_top(matcher, r)
            hits = int((world.person[top] == pid).sum())
            sizes.append(len(top))
            guess += hits / len(top)
            if len(top) == 1 and used > 0:
                claims += 1
                correct += hits
    if n == 0:
        raise RedTeamError("no-target")
    return {"evaluated": True, "reason": None, "n_targets": n, "n_unique_claims": claims,
            "reidentification_rate": round(correct / n, 4), "guess_rate": round(guess / n, 4),
            "median_top_set": float(np.median(sizes)), "n_enriched": enriched if enrich else None,
            "n_aux_sources": aux.n_sources if enrich else None}


BACKGROUND_QIS = [{"kind": "time", "adversary": ["_t"], "protected": ["arrival_ts"], "window": [0, 0]},
                  {"kind": "age", "adversary": ["_age"], "protected": AGE_COLS, "tol": 1},
                  {"kind": "exact", "adversary": ["_place"], "protected": ["municipality"]},
                  {"kind": "sex", "adversary": ["_sex"], "protected": ["sex"]},
                  {"kind": "postcode", "adversary": ["_postcode"], "protected": ["postcode"]}]
BACKGROUND_FROM = {"_t": "arrival_ts", "_place": "municipality", "_sex": "sex", "_postcode": "postcode"}


def _mode(values) -> str | None:
    """Most common non-blank value; ties go to the smallest string (deterministic)."""
    counts: dict = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    return min(counts, key=lambda v: (-counts[v], v)) if counts else None


def sensitive_columns(kit: Path, dataset: str, released: dict) -> dict:
    """``{table: [columns]}``: per released table (``released`` maps table -> released columns, from the release
    contract's rungs), the columns the kit's field catalog marks as sensitive attributes (QI columns excluded)."""
    p = Path(kit) / "metadata" / "field_catalog.csv"
    if not p.is_file():
        raise RedTeamError("no-field-catalog")
    cat = _read(p)
    if not {"dataset", "table", "column", "privacy_role"} <= set(cat.columns):
        raise RedTeamError("no-field-catalog")
    qi_cols = {c for q in BACKGROUND_QIS for c in q["protected"]}
    sel = cat[(cat["dataset"] == dataset) & (cat["privacy_role"] == "sensitive_attribute")]
    out = {}
    for table, cols in sorted(released.items()):
        found = sorted(set(sel.loc[sel["table"] == table, "column"]) & set(cols) - qi_cols)
        if found:
            out[table] = found
    if not out:
        raise RedTeamError("no-sensitive-released")
    return out


def _cells(df: pd.DataFrame, col: str) -> np.ndarray:
    return np.array(["" if _blank(v) else str(v).strip() for v in df[col].tolist()], dtype=object)


def _link_column(rungs: dict, table: str, target: str, target_cols, cols) -> str | None:
    """The column a released table shares with the target table as the same pseudonym (rung id.pseudonym in both),
    e.g. the visit pseudonym of lab rows. Chosen by the release contract's rungs, never by cell shape."""
    shared = sorted(c for c in cols if c in target_cols and rungs.get(table, {}).get(c) == "id.pseudonym"
                    and rungs.get(target, {}).get(c) == "id.pseudonym")
    return shared[0] if len(shared) == 1 else None


def _score(cells: np.ndarray, rows, top_of, base) -> dict:
    """Targets ``rows`` of a column; ``top_of(row)`` -> the candidate rows whose values the attacker votes over."""
    n = ok = b = 0
    for r in rows:
        truth = cells[r]
        if not truth:
            continue
        n += 1
        ok += _mode(cells[top_of(r)]) == truth
        b += base == truth
    if not n:
        return failed(RedTeamError("no-target"), ATTR_KEYS)
    return {"evaluated": True, "reason": None, "n_targets": n, "inference_rate": round(ok / n, 4),
            "baseline_rate": round(b / n, 4)}


def _sample(n: int) -> np.ndarray:
    rows = np.arange(n)
    if n > MAX_SAMPLE:
        rows = np.sort(np.random.default_rng(SEED).choice(n, MAX_SAMPLE, replace=False))
    return rows


def attribute_inference(kit: Path, dataset: str, table: str, world: _World, protected: pd.DataFrame,
                        original: pd.DataFrame, record_key: str, rungs: dict, others: dict | None = None) -> dict:
    """Per released sensitive attribute of every released table: attacker accuracy and base-rate accuracy.

    ``rungs`` is the release contract's ``{table: {column: rung}}``; ``others`` maps each other released table to
    its released rows. Targets of a column are its released rows (a seeded sample of at most MAX_SAMPLE). The
    attacker knows the target visit's exact QIs from the original record; a row of another table inherits the QIs
    of its visit through the shared pseudonym column and the vote runs over the rows of the best-scoring visits.
    Keys: the column name for the target table, ``<table>.<column>`` for the others."""
    others = others or {}
    prot = protected.reset_index(drop=True)
    released = {table: list(prot.columns), **{t: list(df.columns) for t, df in others.items()}}
    by_table = sensitive_columns(kit, dataset, released)
    matcher = Matcher(prot, qis_from_spec(BACKGROUND_QIS, prot.columns), rungs.get(table, {}))
    orig = {str(r[record_key]): r for r in original.to_dict("records")}
    cache: dict = {}

    def visit_top(pr: int) -> np.ndarray:
        o = orig.get(str(world.record[pr]))
        if o is None:
            raise RedTeamError("no-target")
        bg = {k: str(o.get(src, "") or "") for k, src in BACKGROUND_FROM.items()}
        when, _ = _interval_one(bg["_t"].strip()) if bg["_t"].strip() else (None, None)
        birth = _birth(o.get("date_of_birth", ""), False)
        age = _age_at(birth, pd.Timestamp(when)) if birth is not None and when is not None else None
        bg["_age"] = "" if age is None else f"{age:.4f}"
        key = tuple(sorted(bg.items()))
        if key not in cache:
            cache[key] = fs_top(matcher, bg)[0]
        return cache[key]

    out = {}
    for c in by_table.get(table, []):
        cells = _cells(prot, c)
        out[c] = _score(cells, _sample(len(prot)), visit_top, _mode(cells))
    for t in sorted(set(by_table) - {table}):
        df = others[t].reset_index(drop=True)
        link = _link_column(rungs, t, table, prot.columns, df.columns)
        if link is None:
            for c in by_table[t]:
                out[f"{t}.{c}"] = failed(RedTeamError("no-link-to-target-table"), ATTR_KEYS)
            continue
        visit_of = {k: i for i, k in enumerate(_cells(prot, link)) if k}
        keys = _cells(df, link)
        rows_of: dict = {}
        for i, k in enumerate(keys):
            rows_of.setdefault(k, []).append(i)
        linked = np.array([i for i in _sample(len(df)) if keys[i] in visit_of], dtype=int)

        prot_keys, memo = _cells(prot, link), {}

        def lab_top(r: int, keys=keys, visit_of=visit_of, rows_of=rows_of, prot_keys=prot_keys, memo=memo):
            v = visit_of[keys[r]]
            if v not in memo:
                memo[v] = np.array(sorted(i for k in set(prot_keys[visit_top(v)]) for i in rows_of.get(k, ())),
                                   dtype=int)
            return memo[v]

        for c in by_table[t]:
            cells = _cells(df, c)
            out[f"{t}.{c}"] = _score(cells, linked, lab_top, _mode(cells))
    return {"evaluated": True, "reason": None, "columns": out}


# --- release join (#139 r2): the kit's person register joined to the RELEASED rows on the released QIs ------------
# (file under the kit root, national-ID column, birth column, place column, sex column)
REGISTER_SOURCES = (
    ("data/finance/customers.csv", "hetu", "birth_date", "city", None),
    ("data/energy/customers.csv", "hetu", "birth_date", "municipality", None),
    ("data/education/students.csv", "hetu", "birth_date", "municipality", "sex"),
)
REGISTER_QIS = [{"kind": "age", "adversary": ["_age"], "protected": AGE_COLS, "tol": 1},
                {"kind": "exact", "adversary": ["_place"], "protected": ["municipality"]},
                {"kind": "sex", "adversary": ["_sex"], "protected": ["sex"]}]
MID_YEAR = pd.Timestamp("2025-07-01")  # the release year: the register gives no visit date, so age is +-0.5 y
JOIN_KEYS = LINK_KEYS + ("n_register_sources", "linked_table", "linked_n_targets", "linked_reidentification_rate")


def _register(kit: Path) -> tuple:
    """National ID -> {birth, place, sex}, first source with a value wins (fixed source order)."""
    reg: dict = {}
    n = 0
    for rel, nid, birth, place, sex in REGISTER_SOURCES:
        p = Path(kit) / rel
        if not p.is_file():
            continue
        df = _read(p)
        if not {c for c in (nid, birth, place, sex) if c} <= set(df.columns):
            raise RedTeamError("aux-table-malformed")
        n += 1
        for r in df.to_dict("records"):
            k = str(r[nid]).strip()
            if not k:
                continue
            e = reg.setdefault(k, {"_birth": None, "_place": "", "_sex": ""})
            if e["_birth"] is None:
                e["_birth"] = _birth(r[birth], False)
            if not e["_place"] and not _blank(r[place]):
                e["_place"] = str(r[place]).strip()
            if sex and not e["_sex"]:
                e["_sex"] = _SEX.get(str(r[sex]).strip().lower(), "")
    if n == 0:
        raise RedTeamError("no-register")
    return reg, n


def release_join(kit: Path, table: str, world: _World, protected: pd.DataFrame, original: pd.DataFrame,
                 record_key: str, rungs: dict, others: dict | None = None, id_col: str = "patient_hetu") -> dict:
    """Targets: register persons (national ID) with a visit in the release, a seeded sample of at most MAX_SAMPLE.
    Each is scored against the released visits on the released age band, municipality and sex (Fellegi-Sunter).
    Unique re-identification and 1-in-k guess success per person; through the visit pseudonym, the share of the
    targets' released rows of each other released table that sit on a correctly singled-out visit."""
    reg, n_src = _register(kit)
    if id_col not in original.columns:
        raise RedTeamError("no-register")
    person_of = {}
    for rid, nid in zip(original[record_key].astype(str), original[id_col].astype(str)):
        pid = world.id_map.get(rid)
        if pid is not None and nid.strip():
            person_of[nid.strip()] = pid
    ids = sorted(k for k in reg if person_of.get(k) in world.persons)
    if not ids:
        raise RedTeamError("no-target")
    ids = [ids[i] for i in _sample(len(ids))]
    prot = protected.reset_index(drop=True)
    matcher = Matcher(prot, qis_from_spec(REGISTER_QIS, prot.columns), rungs.get(table, {}))
    # the other released table linked to the visits (first by name, deterministic), if any
    link = next(((t, c) for t in sorted(others or {})
                 for c in [_link_column(rungs, t, table, prot.columns, others[t].columns)] if c), None)
    if link:
        lt, lc = link
        visit_key = _cells(prot, lc)
        rows_per_key: dict = {}
        for k in _cells(others[lt].reset_index(drop=True), lc):
            rows_per_key[k] = rows_per_key.get(k, 0) + 1
    n = claims = correct = linked_n = linked_ok = 0
    guess = 0.0
    sizes: list = []
    for nid in ids:
        e, pid = reg[nid], person_of[nid]
        age = _age_at(e["_birth"], MID_YEAR) if e["_birth"] is not None else None
        top, used = fs_top(matcher, {"_age": "" if age is None else f"{age:.4f}", "_place": e["_place"],
                                     "_sex": e["_sex"]})
        n += 1
        hits = int((world.person[top] == pid).sum())
        sizes.append(len(top))
        guess += hits / len(top)
        won = len(top) == 1 and used > 0 and hits == 1
        claims += len(top) == 1 and used > 0
        correct += won
        if link:
            own = np.flatnonzero(world.person == pid)
            linked_n += sum(rows_per_key.get(visit_key[v], 0) for v in own if visit_key[v])
            if won and visit_key[top[0]]:
                linked_ok += rows_per_key.get(visit_key[top[0]], 0)
    out = {"evaluated": True, "reason": None, "n_targets": n, "n_unique_claims": claims,
           "reidentification_rate": round(correct / n, 4), "guess_rate": round(guess / n, 4),
           "median_top_set": float(np.median(sizes)), "n_enriched": None, "n_aux_sources": None,
           "n_register_sources": n_src, "linked_table": None, "linked_n_targets": None,
           "linked_reidentification_rate": None}
    if link and linked_n:
        out.update(linked_table=link[0], linked_n_targets=linked_n,
                   linked_reidentification_rate=round(linked_ok / linked_n, 4))
    return out
