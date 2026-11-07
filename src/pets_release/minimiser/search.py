"""Deterministic bounded search over the detail ladders (spec #1, module 8; D10, D23).

Phases, each in fixed (table, column) order; linked columns move as one unit:
  start        every permitted field at its floor (alternative floors only if the start is rejected)
  withhold     try withholding each released unit; adopt if every purpose check still passes
  coarsen      step each released unit one rung coarser while adopted; the ladders are a partial order, so
               every branch (e.g. ``ts.hour_of_day`` vs the date rungs from ``ts.month_hour``) is walked
               independently and the better branch end is adopted (ties keep the spec-ladder branch)
  joint        the policy's enumerated joint QI moves; adopt only on a strictly better objective
  sacrifice    only if the k shortfall still exceeds the suppression budget: coarsen sacrifice ``via``
               columns and retry joint moves, accepting a policy-enumerated sacrifice at or above its floor
  final        local suppression to reach k, then an uncached re-check of every purpose check and every
               privacy target the policy declares on the full data. k_anonymity (persons) runs ticket 11's k
               checks through 04's runner (no QI released: person-k on one class, unidentified records hit); any other
               kind is unsupported and refuses the plan, as do a raising, refused or incomplete check run.
               A policy declaring no target records privacy ``not_applicable``, never ``pass``

Acceptance: every purpose check status ``ok`` with score >= 0.9. A check below 0.9 is waived only if it is an
enumerated sacrifice, scored (status ok) at or above its floor score, and the candidate differs from the
strict-phase plan only in sacrifice ``via`` columns, at least one of them that check's own. In the final
re-check a drop caused by suppression is also waived for an enumerated sacrifice at or above its floor whose
``via`` column is coarser than its floor, if the check passed strictly before suppression. Errors, not
answerable and missing results are never waived. Objective: minimise the worst risk component, then the
mean; ties prefer the strictly coarser plan on the ladders' partial order (never an incomparable rung), then the
earlier candidate. At most ``budget`` candidate evaluations.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from pets_release.ladders import LADDERS, WITHHELD, apply, at_least_as_coarse, output_column
from pets_release.ladders.rungs import BRANCH_RUNGS
from pets_release.policy.model import validate_plan

from . import risk as R
from .readsets import input_digest, series_digest

LOG_KEYS = frozenset({"step", "candidate_digest", "moves", "scores", "risk", "accepted", "reason", "cached"})
PASS = 0.9
DEFAULT_BUDGET = 100


class MinimiserRefused(Exception):
    """No releasable plan. ``log`` carries the search log (content-free); message is schema-only."""

    def __init__(self, reason: str, log: list | None = None, stats: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.log = list(log or [])
        self.stats = dict(stats or {})


@dataclass
class SearchResult:
    plan: list
    log: list
    suppressed: dict  # {table: tuple of source index labels} (in memory only; never logged)
    final: dict  # aggregate re-check results
    sacrifices: list
    stats: dict
    summary: dict = field(default_factory=dict)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def write_search_log(path, log: list) -> None:
    """One canonical JSON SearchLogEntry per line (UTF-8, LF)."""
    lines = []
    for e in log:
        if set(e) != LOG_KEYS:
            raise ValueError("search log entry has unexpected keys")
        lines.append(canonical(e))
    Path(path).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def apply_suppression(tables: Mapping[str, pd.DataFrame], suppressed: Mapping[str, tuple]) -> dict:
    """Drop suppressed source rows (by index label) from (source or protected) tables."""
    return {t: (df.drop(index=list(suppressed.get(t, ()))) if suppressed.get(t) else df) for t, df in tables.items()}


def _norm(res) -> dict:
    """Purpose result -> {score, status}; anything but a finite score with status ok is not a pass."""
    if not isinstance(res, Mapping):
        return {"score": None, "status": "error"}
    status, score = res.get("status"), res.get("score")
    if status == "ok":
        try:
            score = float(score)
        except (TypeError, ValueError):
            return {"score": None, "status": "error"}
        if not math.isfinite(score):
            return {"score": None, "status": "error"}
        return {"score": score, "status": "ok"}
    return {"score": None, "status": status if status in ("not_answerable", "missing") else "error"}


MAX_SUPPRESSION_ROUNDS = 50


def _units(person_of: pd.Series, rows) -> int:
    """Distinct identified persons plus unidentified records among source rows (ticket 21's unit count)."""
    vals = [person_of.loc[i] for i in sorted(rows)]
    ident = {v for v in vals if isinstance(v, str) and v.strip()}
    return len(ident) + sum(1 for v in vals if not (isinstance(v, str) and v.strip()))


def _call(fn, task, original, protected) -> dict:
    """Run one purpose check; a raise is an ``error`` result (message dropped: it could carry values)."""
    try:
        return _norm(fn(task, original, protected))
    except Exception:  # noqa: BLE001
        return {"score": None, "status": "error"}


def _strict(r) -> bool:
    return r["status"] == "ok" and r["score"] is not None and r["score"] >= PASS


class _Search:
    def __init__(self, policy, tables, keys, *, purpose, purpose_all, kspec, budget, read_sets, params,
                 redactor, risk_extra):
        self.p = policy
        self.src = tables
        self.keys = keys
        self.purpose = purpose
        self.purpose_all = purpose_all
        self.kspec = kspec
        self.budget = budget
        self.read_sets = read_sets
        self.params = params or {}
        self.redactor = redactor
        self.risk_extra = risk_extra
        self.k = R.k_target(policy)
        self.checks = tuple(policy.purpose_checks)
        self.log: list = []
        self.cache: dict = {}
        self.colmemo: dict = {}
        self.digmemo: dict = {}
        self.stats = {"candidates": 0, "cache_hits": 0, "cache_misses": 0, "budget": budget, "bound_reached": False}
        self.sacr = {s["check"]: s for s in policy.sacrifices}
        self.via_all = {(v["table"], v["column"]) for s in policy.sacrifices for v in s["via"]}
        self.floor_rung = {key: f.rung for key, f in policy.floors.items()}
        self.start_ev = self.base_ev = None  # set by run() once the start and the strict phases are adopted
        self._units()
        self._check_inputs()

    # ---------------------------------------------------------------- setup
    def _check_inputs(self):
        unknown = [c for c in self.p.risk_vector if c not in R.BUILTIN_COMPONENTS]
        if unknown and self.risk_extra is None:
            raise MinimiserRefused("risk components without a measurement: " + ",".join(unknown))
        if self.k is None and set(self.p.risk_vector) & R.K_COMPONENTS:
            raise MinimiserRefused("k risk components without a k target")
        if self.k is not None and self.kspec is None:
            raise MinimiserRefused("k target needs a person/record-key spec")
        if not self.checks:
            raise MinimiserRefused("policy names no purpose checks")
        for t, df in self.src.items():
            for c in df.columns:
                if (t, c) not in self.p.floors:
                    raise MinimiserRefused(f"source column {t}.{c} has no policy floor")
        for (t, c) in self.p.floors:
            if t not in self.src or c not in self.src[t].columns:
                raise MinimiserRefused(f"policy column {t}.{c} missing from source")

    def _units(self):
        group = {}
        for g in self.p.linked:
            for key in g:
                group[key] = tuple(sorted(g))
        seen, units = set(), []
        for key in sorted(self.p.floors):
            u = group.get(key, (key,))
            if u[0] in seen:
                continue
            seen.add(u[0])
            units.append(u)
        self.units = units
        self.unit_of = {key: u for u in units for key in u}

    def family(self, key):
        return self.p.floors[key].family

    def ladder(self, key, floor):
        lad = LADDERS[self.family(key)]
        if floor not in lad:  # alternative floor: that rung or withheld only
            return (floor, WITHHELD)
        return tuple(r for r in lad[lad.index(floor):] if at_least_as_coarse(r, floor))  # skip incomparable rungs

    def rung_params(self, key, rung):
        """Params for ``rung`` on ``key``, or None if the rung cannot be parameterised (skipped)."""
        given = self.params.get(key, {}).get(rung)
        if given is not None:
            return dict(given)
        if rung in ("age.band5", "age.band10"):
            return None
        if rung == "id.pseudonym":
            return {"label": "RECORD_KEY"}
        if rung == "geo.topn":
            pm = self.p.param_minimums.get(key)
            return {"n": pm["min"] if pm and pm["rung"] == rung else 8}
        if rung == "num.round":
            return {"unit": 1}
        if rung == "num.bin":
            return {"width": 10}
        return {}

    # ---------------------------------------------------------------- candidates
    def entry_state(self, cand, key):
        return cand[key]  # (rung, params_json, floor)

    def plan_of(self, cand, reasons=None) -> list:
        out = []
        for key in sorted(cand):
            rung, pj, floor = cand[key]
            out.append({"table": key[0], "column": key[1], "rung": rung, "params": json.loads(pj), "floor": floor,
                        "reason": (reasons or {}).get(key) or self.p.floors[key].reason, "source": "search"})
        return out

    def digest(self, cand) -> str:
        return hashlib.sha256(canonical([[k[0], k[1], *cand[k][:2]] for k in sorted(cand)]).encode()).hexdigest()

    def dominates(self, a, b) -> bool:
        """``a`` is strictly coarser than ``b``: every column at a rung at least as coarse (the ladders' partial
        order, so incomparable rungs such as ``ts.hour_of_day`` vs ``ts.day`` never count), one strictly."""
        strict = False
        for key in b:
            ra, rb = a[key][0], b[key][0]
            if ra == rb:
                continue
            if not at_least_as_coarse(ra, rb):
                return False
            strict = True
        return strict

    def column(self, key, rung, pj, floor):
        """(output name, Series) via ticket 07's apply on a one-column plan (memoised)."""
        mk = (key, rung, pj)
        if mk not in self.colmemo:
            t, c = key
            src = self.src[t]
            plan = [{"table": t, "column": cc, "rung": WITHHELD, "params": {}, "floor": WITHHELD} for cc in src.columns
                    if cc != c]
            e = {"table": t, "column": c, "rung": rung, "params": json.loads(pj), "floor": floor}
            plan.append(e)
            out = apply(plan, {t: src}, self.keys, redactor=self.redactor)
            name = output_column(e)
            self.colmemo[mk] = (name, out[t][name])
            self.digmemo[mk] = series_digest(out[t][name])
        return self.colmemo[mk]

    def protected(self, cand) -> dict:
        out = {}
        for t in sorted(self.src):
            src = self.src[t]
            cols = {}
            for c in src.columns:
                rung, pj, floor = cand[(t, c)]
                if rung == WITHHELD:
                    continue
                name, s = self.column((t, c), rung, pj, floor)
                if name in cols or (name != c and name in src.columns):
                    raise MinimiserRefused(f"output column collision in {t}")
                cols[name] = s
            if cols:
                out[t] = pd.DataFrame(cols, index=src.index)
        return out

    def k_view(self, prot) -> dict:
        """Protected tables for the k checks: the person table is always present (rows only, if none of its
        columns is released), so person-k sees every released person and unidentified record."""
        pt = self.kspec["person"]["table"] if self.kspec else None
        if pt is None or pt in prot:
            return prot
        return {**prot, pt: pd.DataFrame(index=self.src[pt].index)}

    def _col_digester(self, cand):
        by_out = {}
        for (t, c), (rung, pj, _) in cand.items():
            if rung != WITHHELD:
                name = self.colmemo[((t, c), rung, pj)][0]
                by_out[(t, name)] = self.digmemo[((t, c), rung, pj)]

        def dig(t, c):
            return by_out.get((t, c))

        def tables():
            tb = {}
            for (t, c) in sorted(by_out):
                tb.setdefault(t, []).append(c)
            return sorted(tb.items())

        dig.tables = tables
        return dig

    # ---------------------------------------------------------------- evaluation
    def evaluate(self, cand):
        """Purpose results (cached by candidate-input digest), risk vector, person-k."""
        self.stats["candidates"] += 1
        prot = self.protected(cand)
        dig = self._col_digester(cand)
        results, hits = {}, 0
        for chk in self.checks:
            ck = input_digest(chk, self.read_sets, dig)
            if ck in self.cache:
                results[chk] = self.cache[ck]
                hits += 1
                self.stats["cache_hits"] += 1
            else:
                r = _call(self.purpose, chk, self.src, prot)
                self.cache[ck] = r
                results[chk] = r
                self.stats["cache_misses"] += 1
        plan = self.plan_of(cand)
        rv, pk = R.risk_vector(self.p, plan, self.k_view(prot), self.src, self.kspec, self.k)
        if self.risk_extra is not None:
            extra = self.risk_extra(plan, prot)
            for c in self.p.risk_vector:
                if c not in rv:
                    if c not in extra:
                        raise MinimiserRefused(f"risk component {c} not measured")
                    rv[c] = float(extra[c])
        rv = {c: rv[c] for c in self.p.risk_vector}
        return {"results": results, "risk": rv, "cached": hits == len(self.checks), "pk": pk}

    def risk_key(self, ev):
        vals = list(ev["risk"].values()) or [0.0]
        return (max(vals), sum(vals) / len(vals))

    def better(self, ev, cand, ev_ref, ref) -> bool:
        """Strictly better objective: lower (worst, mean) risk; on a tie, strictly coarser on the partial order.
        Incomparable plans with equal risk are not better (the earlier candidate is kept)."""
        a, b = self.risk_key(ev), self.risk_key(ev_ref)
        return a < b or (a == b and self.dominates(cand, ref))

    def failing(self, results):
        return sorted(c for c, r in results.items() if not _strict(r))

    def sacrifice_ok(self, results, cand, base):
        """Every non-strict result is a waivable enumerated sacrifice for this candidate (see module doc)."""
        fails = self.failing(results)
        if not fails:
            return True
        if base is None:
            return False
        diff = {k for k in cand if cand[k][:2] != base[k][:2]}
        if not diff or not diff <= self.via_all:
            return False
        for c in fails:
            r, s = results[c], self.sacr.get(c)
            if s is None or r["status"] != "ok" or r["score"] is None or r["score"] < s["floor_score"]:
                return False
            if not diff & {(v["table"], v["column"]) for v in s["via"]}:
                return False
        return True

    def final_ok(self, results, cand, base, pre):
        """Re-check after suppression: each non-strict result must be an enumerated sacrifice, status ok, at or
        above its floor, and either waived for the adopted candidate in the search (the move rule) or caused by
        suppression: it passed strictly on the unsuppressed candidate and one of its via columns is coarser than
        its floor (the sacrifice is in effect). Errors and unknowns are never waived."""
        diff = {k for k in cand if cand[k][:2] != base[k][:2]}
        if diff and not diff <= self.via_all:
            return False
        for c in self.failing(results):
            r, s = results[c], self.sacr.get(c)
            if s is None or r["status"] != "ok" or r["score"] is None or r["score"] < s["floor_score"]:
                return False
            via = {(v["table"], v["column"]) for v in s["via"]}
            by_move = bool(diff & via)
            in_effect = any(self._coarser_than_floor(k, cand[k][0]) for k in via)
            # _strict(pre[c]) is defensive: the strict phases leave every check passing, and a sacrifice-phase
            # failure is already covered by by_move; kept so a future phase cannot widen the waiver.
            by_suppression = c in pre and _strict(pre[c]) and in_effect
            if not (by_move or by_suppression):
                return False
        return True

    def _coarser_than_floor(self, key, rung) -> bool:
        """``rung`` lies strictly coarser than the policy floor on the family ladder (an alternative floor, or a
        rung or floor off the ladder, is never coarser)."""
        lad = LADDERS[self.family(key)]
        fl = self.floor_rung[key]
        return rung in lad and fl in lad and rung != fl and at_least_as_coarse(rung, fl)

    # ---------------------------------------------------------------- logging
    def moves(self, cand, cur):
        out = []
        for key in sorted(cand):
            if cur is None:
                if cand[key][0] == WITHHELD and cand[key][2] == WITHHELD:
                    continue
            elif cand[key][:2] == cur[key][:2]:
                continue
            out.append({"table": key[0], "column": key[1], "rung": cand[key][0]})
        return out

    def record(self, cand, cur, ev, accepted, reason, step=None):
        e = {
            "step": len([x for x in self.log if x["step"] != "final"]) if step is None else step,
            "candidate_digest": self.digest(cand),
            "moves": self.moves(cand, cur),
            "scores": {c: ev["results"][c]["score"] if c in ev["results"] else None for c in self.checks},
            "risk": dict(ev["risk"]),
            "accepted": bool(accepted),
            "reason": reason,
            "cached": bool(ev["cached"]),
        }
        self.log.append(e)
        return e["step"]

    def out_of_budget(self):
        if self.stats["candidates"] >= self.budget:
            self.stats["bound_reached"] = True
            return True
        return False

    # ---------------------------------------------------------------- phases
    def run(self) -> SearchResult:
        start = {}
        for key in sorted(self.p.floors):
            fl = self.floor_rung[key]
            pj = canonical(self.rung_params(key, fl) or {}) if fl != WITHHELD else "{}"
            if fl not in (WITHHELD,) and self.rung_params(key, fl) is None:
                raise MinimiserRefused(f"no params for floor rung of {key[0]}.{key[1]}")
            start[key] = (fl, pj, fl)
        ev = self.evaluate(start)
        ok = not self.failing(ev["results"])
        self.record(start, None, ev, ok, "start: every permitted field at its floor: "
                    + ("adopted" if ok else "rejected (" + ",".join(self.failing(ev["results"])) + ")"))
        if not ok and self.p.alt_floors:
            alt = dict(start)
            for key, rung in sorted(self.p.alt_floors.items()):
                pr = self.rung_params(key, rung)
                if pr is None:
                    continue
                for k2 in self.unit_of[key]:
                    alt[k2] = (rung, canonical(pr), rung)
            ev = self.evaluate(alt)
            ok = not self.failing(ev["results"])
            self.record(alt, start, ev, ok, "start: alternative floors released: "
                        + ("adopted" if ok else "rejected (" + ",".join(self.failing(ev["results"])) + ")"))
            if ok:
                start = alt
        if not ok:
            raise MinimiserRefused("no accepted candidate: the start plan fails a purpose check", self.log, self.stats)
        self.start_ev = ev
        cur, cur_ev = start, ev
        reasons: dict = {}

        def step_reason(key, text, step):
            for k2 in self.unit_of[key]:
                reasons[k2] = f"search step {step}: {text}"

        def try_strict(cand, desc, strictly_better=False):
            nonlocal cur, cur_ev
            ok, ev, step = self._attempt_strict(cand, cur, cur_ev, desc, strictly_better)
            if ok:
                cur, cur_ev = cand, ev
            return ok, step

        # withholding pass
        for u in self.units:
            if self.out_of_budget():
                break
            if cur[u[0]][0] == WITHHELD:
                continue
            cand = dict(cur)
            for key in u:
                cand[key] = (WITHHELD, "{}", cur[key][2])
            ok, step = try_strict(cand, f"withhold {self._name(u)}")
            if ok:
                step_reason(u[0], "withheld; every purpose check passes without it", step)
        # coarsening pass: walk every branch of the unit's ladder (partial order) from the current rung
        for u in self.units:
            end = self._walk(u, cur, cur_ev, self._attempt_strict, "coarsen", lambda ev: True)
            if end is not None:
                cur, cur_ev, step = end
                step_reason(u[0], f"{cur[u[0]][0]}: coarsest rung at which every purpose check passes", step)
        # joint QI moves
        for i, mv in enumerate(self.p.joint_qi_moves):
            if self.out_of_budget():
                break
            cand = self._joint(mv, cur)
            if cand is None or cand == cur:
                continue
            ok, step = try_strict(cand, f"joint QI move {i + 1}", strictly_better=True)
            if ok:
                for m in mv:
                    step_reason((m["table"], m["column"]), f"{m['rung']}: joint QI move {i + 1} lowers risk", step)
        base = cur
        self.base_ev = cur_ev
        # sacrifice phase
        if self.p.sacrifices and self._needs_more(cur_ev):
            def attempt_sacrifice(cand, state, state_ev, desc):
                ev2, step = self._try_sacrifice(cand, state, state_ev, base, desc)
                return ev2 is not None, ev2, step

            for u in self.units:
                if not set(u) <= self.via_all:
                    continue
                end = self._walk(u, cur, cur_ev, attempt_sacrifice, "sacrifice: coarsen", self._needs_more)
                if end is not None:
                    cur, cur_ev, step = end
                    step_reason(u[0], f"{cur[u[0]][0]}: enumerated sacrifice to reach k", step)
            for i, mv in enumerate(self.p.joint_qi_moves):
                if not self._needs_more(cur_ev) or self.out_of_budget():
                    break
                cand = self._joint(mv, cur)
                if cand is None or cand == cur:
                    continue
                ev2, step = self._try_sacrifice(cand, cur, cur_ev, base, f"sacrifice: joint QI move {i + 1}")
                if ev2:
                    cur, cur_ev = cand, ev2
                    for m in mv:
                        step_reason((m["table"], m["column"]), f"{m['rung']}: joint QI move {i + 1}, enumerated sacrifice", step)
        return self.finish(cur, base, reasons, cur_ev)

    def _try_sacrifice(self, cand, cur, cur_ev, base, desc):
        ev = self.evaluate(cand)
        ok = self.sacrifice_ok(ev["results"], cand, base) and self.better(ev, cand, cur_ev, cur)
        fails = self.failing(ev["results"])
        why = "adopted" + (" (sacrificing " + ",".join(fails) + ")" if fails else "") if ok else (
            "rejected (" + ",".join(fails) + " not a waivable sacrifice)" if fails and not self.sacrifice_ok(
                ev["results"], cand, base) else "rejected (objective not improved)")
        step = self.record(cand, cur, ev, ok, f"{desc}: {why}")
        return (ev if ok else None), step

    def _needs_more(self, ev):
        sh = ev["risk"].get("qi_k_shortfall")
        if sh is None:
            if self.k is None:
                return False
            sh = self._shortfall(ev)
        budget = (self.p.suppression or {}).get("max_share", 0.0)
        return sh > budget

    def _shortfall(self, ev):
        pk = ev["pk"]
        if pk is None:
            return 0.0
        n = len(pk.per_person) + pk.unidentified
        return (sum(1 for v in pk.per_person.values() if v < self.k) + pk.unidentified) / n if n else 1.0

    def _name(self, u):
        return "+".join(f"{t}.{c}" for t, c in u)

    def _attempt_strict(self, cand, ref, ref_ev, desc, strictly_better=False):
        """Measure ``cand`` against ``ref``: every purpose check strict, and risk no worse (or, for joint
        moves, a strictly better objective). Returns (ok, ev, step); the caller adopts."""
        ev = self.evaluate(cand)
        fails = self.failing(ev["results"])
        better = (self.better(ev, cand, ref_ev, ref) if strictly_better
                  else self.risk_key(ev) <= self.risk_key(ref_ev))
        ok = not fails and better
        why = "adopted" if ok else ("rejected (" + ",".join(fails) + " below 0.9 or not ok)" if fails
                                    else "rejected (objective not improved)")
        return ok, ev, self.record(cand, ref, ev, ok, f"{desc}: {why}")

    def _successors(self, key, state):
        """Immediate coarser rungs (with params, never ``withheld``) of the column's current rung on the
        partial order bounded by its floor; spec-ladder rungs first, then branch rungs (e.g. from
        ``ts.month_hour``: ``ts.day``, then ``ts.hour_of_day``)."""
        rung, _, floor = state[key]
        within = self.ladder(key, floor)
        above = [r for r in self.ladder(key, rung) if r not in (rung, WITHHELD) and r in within
                 and self.rung_params(key, r) is not None]
        nxt = [s for s in above if not any(t != s and s in self.ladder(key, t) for t in above)]
        lad = LADDERS[self.family(key)]
        return sorted(nxt, key=lambda r: (r in BRANCH_RUNGS, lad.index(r)))

    def _walk(self, u, state, ev, attempt, label, cont):
        """Walk every branch from ``state`` one rung at a time while ``attempt`` accepts and ``cont`` holds.
        Each branch is explored independently; its end is compared with the others by ``better`` (the first
        branch wins ties, also incomparable ones). Steps on a branch not chosen are re-marked not accepted.
        Returns (state, ev, step of the adopted rung) or None if nothing was accepted."""
        key = u[0]
        if state[key][0] == WITHHELD or not cont(ev):
            return None
        best, best_entries = None, []
        for r2 in self._successors(key, state):
            if self.out_of_budget():
                break
            pj = canonical(self.rung_params(key, r2))
            cand = dict(state)
            for k2 in u:
                cand[k2] = (r2, pj, state[k2][2])
            n0 = len(self.log)
            ok, ev2, step = attempt(cand, state, ev, f"{label} {self._name(u)} to {r2}")
            if not ok:
                continue
            end = self._walk(u, cand, ev2, attempt, label, cont) or (cand, ev2, step)
            entries = [e for e in self.log[n0:] if e["accepted"]]
            if best is None or self.better(end[1], end[0], best[1], best[0]):
                self._unadopt(best_entries, end[0][key][0])
                best, best_entries = end, entries
            else:
                self._unadopt(entries, best[0][key][0])
        return best

    @staticmethod
    def _unadopt(entries, kept):
        for e in entries:
            e["accepted"] = False
            e["reason"] = e["reason"].rsplit(": ", 1)[0] + f": measured, not adopted (branch ending at {kept} kept)"

    def _joint(self, mv, cur):
        cand = dict(cur)
        for m in mv:
            key = (m["table"], m["column"])
            floor = cur[key][2]
            if cur[key][0] == WITHHELD:
                return None  # a joint move never re-releases a withheld field
            lad = self.ladder(key, floor)
            if m["rung"] not in lad:
                return None
            pr = self.rung_params(key, m["rung"]) if m["rung"] != WITHHELD else {}
            if pr is None:
                return None
            for k2 in self.unit_of[key]:
                cand[k2] = (m["rung"], canonical(pr), floor)
        return cand

    # ---------------------------------------------------------------- final
    def finish(self, cur, base, reasons, cur_ev) -> SearchResult:
        plan = self.plan_of(cur, reasons)
        validate_plan(plan, self.p)
        bound = (f"; bound of {self.budget} candidates reached, best accepted candidate kept"
                 if self.stats["bound_reached"] else "")
        full = self.protected(cur)
        suppressed, sup_persons, persons = self.suppress(self.k_view(full), plan)
        budget = (self.p.suppression or {}).get("max_share")
        prot = apply_suppression(full, suppressed)
        kprot = apply_suppression(self.k_view(full), suppressed)
        results = self._final_purpose(prot)
        priv, targets, pstatus = self._final_privacy(kprot, plan)
        rv, _ = R.risk_vector(self.p, plan, kprot, self.src, self.kspec, self.k)
        if self.risk_extra is not None:
            ex = self.risk_extra(plan, prot)
            rv.update({c: float(ex[c]) for c in self.p.risk_vector if c not in rv and c in ex})
        rv = {c: rv.get(c) for c in self.p.risk_vector}
        problems = []
        share = sup_persons / persons if persons else 0.0
        if self.k is not None and sup_persons and budget is None:
            problems.append("k not reached and the policy allows no suppression")
        if budget is not None and share > budget:
            problems.append(f"suppression of {sup_persons} of {persons} persons exceeds the policy budget")
        missing = [c for c in self.checks if c not in results]
        if missing:
            problems.append("re-check missing purpose checks: " + ",".join(missing))
        fails = [c for c, r in results.items() if not _strict(r)]
        if fails and not self.final_ok(results, cur, base, cur_ev["results"]):
            problems.append("re-check fails: " + ",".join(sorted(fails)))
        problems += [f"re-check privacy target {t['id']} ({t['kind']}): {t['status']}" for t in targets
                     if t["status"] != "pass"]
        ok = not problems
        ev = {"results": {c: results.get(c, {"score": None, "status": "missing"}) for c in self.checks},
              "risk": {c: (0.0 if v is None else v) for c, v in rv.items()}, "cached": False}
        reason = (f"final: local suppression of {sup_persons} of {persons} persons, then full uncached re-check of "
                  f"every purpose check and every privacy target (privacy {pstatus}): "
                  + ("passed" if ok else "; ".join(problems)) + bound)
        self.record(cur, cur, ev, ok, reason, step="final")
        if not ok:
            raise MinimiserRefused("; ".join(problems), self.log, self.stats)
        sacrifices = []
        for c in sorted(fails):
            s = self.sacr[c]
            # score just before the sacrifice took effect: the unsuppressed adopted candidate when suppression
            # caused the drop, else the strict-phase plan (before any sacrifice move)
            pre = cur_ev["results"].get(c)
            before = pre["score"] if pre is not None and _strict(pre) else self.base_ev["results"][c]["score"]
            sacrifices.append({"check": c, "floor_score": s["floor_score"], "reason": s["reason"],
                               "via": [dict(v) for v in s["via"]],
                               "score_before": before,
                               "score_after": results[c]["score"]})
        final = {
            "purpose": [{"id": c, **results[c]} for c in sorted(results)],
            "privacy": priv,
            "privacy_targets": targets,
            "privacy_status": pstatus,
            "risk": rv,
            "persons": persons,
            "suppressed_persons": sup_persons,
            "suppressed_rows": {t: len(v) for t, v in sorted(suppressed.items())},
        }
        summary = {"start_scores": {c: self.start_ev["results"][c]["score"] for c in self.checks},
                   "start_risk": dict(self.start_ev["risk"]), "final_risk": rv}
        return SearchResult(plan=plan, log=self.log, suppressed=suppressed, final=final, sacrifices=sacrifices,
                            stats=dict(self.stats), summary=summary)

    def _final_privacy(self, kprot, plan):
        """Re-check every privacy target the policy declares, failing closed.

        Returns (k gate summary or None, [{id, kind, status}] sorted by id, overall status). A target passes only
        if it was evaluated and held; a kind the minimiser cannot evaluate is ``unsupported``, a raising,
        refused or incomplete check run is ``error``. No declared target: ``not_applicable``, never ``pass``.
        """
        priv, out = None, []
        for t in sorted(self.p.privacy_targets, key=lambda x: str(x.get("id"))):
            kind = t.get("kind")
            if kind == "k_anonymity" and t.get("unit") == "persons":
                status, priv = self._final_k(kprot, plan)
            else:
                status = "unsupported"
            out.append({"id": t.get("id"), "kind": kind, "status": status})
        overall = "not_applicable" if not out else ("pass" if all(r["status"] == "pass" for r in out) else "fail")
        return priv, out, overall

    def _final_k(self, kprot, plan):
        """Production k checks through 04's runner on the suppressed candidate (person table always present).
        Required: person-k, plus row-k when a QI is released (``R.k_checks_for``); each must be ``pass``."""
        if self.k is None or self.kspec is None:
            return "error", None
        names = R.k_checks_for(R.contract_for(self.p, plan, self.k))
        try:
            priv = R.gate_k(kprot, plan, self.p, self.src, self.kspec, self.k)
        except Exception:  # noqa: BLE001 - the message could carry values
            return "error", None
        if not isinstance(priv, Mapping) or priv.get("refused") is not False or priv.get("registryError") is not None:
            return "error", (dict(priv) if isinstance(priv, Mapping) else None)
        recs = {r.get("check"): r.get("status") for r in priv.get("records") or [] if isinstance(r, Mapping)}
        got = [recs.get(name) for name in names]
        if all(s == "pass" for s in got):
            return "pass", dict(priv)
        return ("fail" if all(s in ("pass", "fail") for s in got) else "error"), dict(priv)

    def _final_purpose(self, prot) -> dict:
        if self.purpose_all is not None:
            try:
                raw = list(self.purpose_all(self.src, prot))
            except Exception:  # noqa: BLE001 - the message could carry values; every check counts as error
                return {c: {"score": None, "status": "error"} for c in self.checks}
            # every returned task is judged; one outside the policy list is never an enumerated sacrifice
            return {r.get("id"): _norm(r) for r in raw}
        return {c: _call(self.purpose, c, self.src, prot) for c in self.checks}

    def suppress(self, full, plan):
        """Local suppression to reach k: drop all rows of persons below k (and their joined rows) to a fixpoint."""
        # Same rule as ticket 21 (run/suppress.py): unit persons, k from the policy, every below-k unit (and
        # every unidentified unit) dropped per round with its joined rows, to a fixpoint (<= 50 rounds); the
        # share is units suppressed / units in the unsuppressed candidate.
        pt = self.kspec["person"]["table"] if self.kspec else None
        if self.k is None or pt not in full:
            return {}, 0, 0
        sup_cfg = self.p.suppression
        if sup_cfg is not None:
            if sup_cfg["unit"] != "persons" or sup_cfg["method"] != "local_suppression":
                raise MinimiserRefused("unsupported suppression method", self.log, self.stats)
            if sup_cfg["k"] != self.k:
                raise MinimiserRefused("suppression k differs from the k target", self.log, self.stats)
        pcol = self.kspec["person"]["column"]
        person_of = self.src[pt][pcol]
        dropped_p: set = set()
        units_before, rounds = None, 0
        while True:
            cur = apply_suppression(full, self._expand(dropped_p))
            pk, _ = R.person_k(cur, plan, self.p, self.src, self.kspec, self.k)
            if pk is None:
                break
            if units_before is None:
                units_before = len(pk.per_person) + pk.unidentified
            rows = sorted(set(pk.below_rows) | set(pk.unidentified_rows))
            if not rows:
                break
            rounds += 1
            if rounds > MAX_SUPPRESSION_ROUNDS:
                raise MinimiserRefused("suppression did not reach a fixpoint", self.log, self.stats)
            if sup_cfg is None:  # no suppression allowed: report the shortfall, drop nothing
                ids = {cur[pt].index[i] for i in rows}
                return {}, _units(person_of, ids), int(units_before)
            idx = cur[pt].index
            dropped_p |= {idx[i] for i in rows}
        sup = self._expand(dropped_p)
        return sup, _units(person_of, dropped_p), int(units_before or 0)

    def _expand(self, person_rows: set) -> dict:
        """Suppressed person-table rows -> {table: sorted index labels}, incl. rows joined to them."""
        if not person_rows:
            return {}
        pt = self.kspec["person"]["table"]
        out = {pt: tuple(sorted(person_rows))}
        for j in self.kspec.get("joins", []):
            if j["ref_table"] != pt or j["table"] not in self.src:
                continue
            refs = set(self.src[pt].loc[list(person_rows), j["ref_column"]])
            child = self.src[j["table"]]
            out[j["table"]] = tuple(sorted(child.index[child[j["column"]].isin(refs)]))
        return out


def search(policy, tables: Mapping[str, pd.DataFrame], keys, *, purpose: Callable, purpose_all: Callable | None = None,
           kspec: Mapping | None = None, budget: int = DEFAULT_BUDGET, read_sets: Mapping | None = None,
           params: Mapping | None = None, redactor=None, risk_extra: Callable | None = None) -> SearchResult:
    """Run the bounded search. Raises ``MinimiserRefused`` (with the log) when no releasable plan exists.

    purpose(task_id, original, protected) -> {score, status}; purpose_all(original, protected) -> [{id, score,
    status}] runs every scenario task for the final re-check (default: ``purpose`` per policy check).
    kspec = {person: {table, column}, record_keys: {table: col}, joins: [...]} (ticket 11's context shape).
    params = {(table, column): {rung: params}} overrides rung parameters (age rungs need ``ref_column``).
    """
    if not isinstance(budget, int) or budget < 1:
        raise ValueError("budget must be a positive integer")
    s = _Search(policy, tables, keys, purpose=purpose, purpose_all=purpose_all, kspec=kspec, budget=budget,
                read_sets=dict(read_sets or {}), params=params, redactor=redactor, risk_extra=risk_extra)
    return s.run()
