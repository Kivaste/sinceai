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
                     "no-target", "no-attack-spec"})
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


def sensitive_columns(kit: Path, dataset: str, table: str, protected: pd.DataFrame) -> list:
    """Released columns the kit's field catalog marks as sensitive attributes (QI columns excluded)."""
    p = Path(kit) / "metadata" / "field_catalog.csv"
    if not p.is_file():
        raise RedTeamError("no-field-catalog")
    cat = _read(p)
    if not {"dataset", "table", "column", "privacy_role"} <= set(cat.columns):
        raise RedTeamError("no-field-catalog")
    qi_cols = {c for q in BACKGROUND_QIS for c in q["protected"]}
    sel = cat[(cat["dataset"] == dataset) & (cat["table"] == table) & (cat["privacy_role"] == "sensitive_attribute")]
    cols = sorted(set(sel["column"]) & set(protected.columns) - qi_cols)
    if not cols:
        raise RedTeamError("no-sensitive-released")
    return cols


def attribute_inference(kit: Path, dataset: str, table: str, world: _World, protected: pd.DataFrame,
                        original: pd.DataFrame, record_key: str, rungs: dict) -> dict:
    """Targets: released visits (a seeded sample of at most MAX_SAMPLE); the attacker knows each target's exact
    QIs from the original record. Per sensitive column: attacker accuracy and base-rate accuracy."""
    prot = protected.reset_index(drop=True)
    cols = sensitive_columns(kit, dataset, table, prot)
    matcher = Matcher(prot, qis_from_spec(BACKGROUND_QIS, prot.columns), rungs)
    orig = {str(r[record_key]): r for r in original.to_dict("records")}
    rows = np.arange(len(prot))
    if len(rows) > MAX_SAMPLE:
        rows = np.sort(np.random.default_rng(SEED).choice(len(rows), MAX_SAMPLE, replace=False))
    cells = {c: np.array(["" if _blank(v) else str(v).strip() for v in prot[c].tolist()], dtype=object) for c in cols}
    base = {c: _mode(cells[c]) for c in cols}
    tally = {c: [0, 0, 0] for c in cols}  # targets, attacker right, base rate right
    cache: dict = {}
    for pr in rows:
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
        top = cache[key]
        for c in cols:
            truth = cells[c][pr]
            if not truth:
                continue
            t = tally[c]
            t[0] += 1
            t[1] += _mode(cells[c][top]) == truth
            t[2] += base[c] == truth
    out = {}
    for c in cols:
        n, ok, b = tally[c]
        out[c] = ({"evaluated": True, "reason": None, "n_targets": n, "inference_rate": round(ok / n, 4),
                   "baseline_rate": round(b / n, 4)} if n else failed(RedTeamError("no-target"), ATTR_KEYS))
    return {"evaluated": True, "reason": None, "columns": out}
