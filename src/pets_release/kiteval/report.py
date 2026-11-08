"""Scorecard report gate. The kit exits 0 on errors and trusts empty denominators; this does not.

Fail closed: a record that is absent, incomplete, errored or unavailable is a rejection."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from numbers import Integral, Real

# Allowlist of exported top-level fields. Everything else stays in the scoring folder.
EXPORT_FIELDS = ("scenario", "dataset", "privacy", "utility", "composite", "tasks", "risks", "tables",
                 "not_applicable")
BASELINE_SECTIONS = ("k_anonymity", "risks", "regex_residuals", "direct_identifiers_retained")
SECTIONS = ("free_text", "linkage", "k_anonymity", "hash_attack", "trajectory_unicity", "table")

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # scenario, dataset, task and table names
_RISK_KEY = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ :<>=()./+-]{0,119}")
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class ScorecardRejected(ValueError):
    """The report is not a clean, complete result. `reason` is a short content-free code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _num(v) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool) and not math.isnan(v) and not math.isinf(v)


def _int(v) -> bool:
    return isinstance(v, Integral) and not isinstance(v, bool)


def _name(v) -> bool:
    return isinstance(v, str) and _ID.fullmatch(v) is not None


def _scenario_id(report: dict):
    s = report.get("scenario")
    return s.get("id") if isinstance(s, dict) else None


# `evaluated: False` reasons that mean "the attack/evaluation has nothing to act on", taken from the
# pets-eval 1.0.0 source (attacks.py, privacy.py, scorecard.py). Anything else is a fail.
# Trajectory outcomes are NOT here: they are benign only when the release provably lacks the input
# columns (see _trajectory_unavailable).
BENIGN_REASONS = {
    "no overlapping quasi-identifiers between adversary and protected table": "no_overlapping_qi",
    "no gold spans in package": "no_gold_spans",
    "no values": "no_values",
}
BENIGN_NOTES = {
    "no catalogued quasi-identifier kept": "no_quasi_identifier",
    "no attack spec targets this table (metadata/attack_specs.json)": "no_attack_spec",
}
_CODE = re.compile(r"[a-z_]{1,40}")


def _walk(node, path=()):
    """Yield (path, dict) for every dict nested anywhere in the node."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, (*path, str(k)))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, (*path, str(i)))


def _trajectory_unavailable(path, reason, expected: dict):
    """Code for an unavailable trajectory evaluation, only if the release lacks the input columns."""
    spec = (expected.get("trajectories") or {}).get(path[1]) if len(path) == 2 else None
    cols = set(expected.get("columns", ()))
    if spec is None:
        return None
    if reason == "user or time column missing" and spec["time"] not in cols:
        return "trajectory_time_removed"
    if reason == "no location column" and not (set(spec["location"]) & cols):
        return "trajectory_location_removed"
    return None


def _scan_nested(name: str, table: dict, expected: dict, found: list) -> None:
    required_text = set(expected.get("free_text", ()))
    """Errored or unavailable sub-results anywhere in a table record are a fail, except the
    allowlisted benign ones, which are recorded as not_applicable."""
    for path, d in _walk(table):
        if "error" in d or "trace" in d:
            raise ScorecardRejected("error_status")
        note = d.get("note")
        if isinstance(note, str):
            if note.lower().startswith("no row map"):
                raise ScorecardRejected("not_evaluated")
            if note in BENIGN_NOTES:
                found.append({"table": name, "section": path[0] if path else "table",
                              "key": path[-1] if len(path) > 1 else "", "code": BENIGN_NOTES[note]})
        if d.get("evaluated") is False:
            reason = d.get("reason")
            if isinstance(reason, str) and reason.lower().startswith("error"):
                raise ScorecardRejected("error_status")
            if path[:1] == ("trajectory_unicity",) and isinstance(reason, str):
                code = _trajectory_unavailable(path, reason, expected)
                if code is None:
                    raise ScorecardRejected("not_evaluated")
                found.append({"table": name, "section": "trajectory_unicity", "key": path[-1], "code": code})
                continue
            if not isinstance(reason, str) or reason not in BENIGN_REASONS:
                raise ScorecardRejected("not_evaluated")
            if path[:1] == ("free_text",) and len(path) > 1 and path[1] in required_text:
                raise ScorecardRejected("required_not_evaluated")
            found.append({"table": name, "section": path[0] if path else "table",
                          "key": path[-1] if path else "", "code": BENIGN_REASONS[reason]})

def _check_tasks(report: dict, required_tasks: list[str]) -> list[dict]:
    utility = report.get("utility")
    if not isinstance(utility, list):
        raise ScorecardRejected("structure")
    by_id = {}
    for u in utility:
        if not isinstance(u, dict) or not _name(u.get("id")):
            raise ScorecardRejected("structure")
        by_id[u["id"]] = u
    if any(u.get("metric") == "error" for u in utility):
        raise ScorecardRejected("error_status")
    for tid in required_tasks:
        if tid not in by_id:
            raise ScorecardRejected("missing_task")
    out = []
    required = set(required_tasks)
    for u in utility:
        is_required = u.get("required") is True or u["id"] in required
        scored = _num(u.get("score")) and 0.0 <= u["score"] <= 1.0
        if is_required and not scored:
            raise ScorecardRejected("not_scored")
        out.append({"id": u["id"], "score": float(u["score"]) if scored else None,
                    "required": is_required, "status": "ok" if scored else "not_answerable"})
    return out


def _positive(v) -> bool:
    return _num(v) and v > 0


def _check_expected_linkage(tr: dict, linkage_expectation) -> None:
    """Every attack the kit should have run for this table has a result, or the kit says why none apply."""
    if linkage_expectation is None:
        return
    linkage = tr.get("linkage")
    if not isinstance(linkage, dict) or not linkage:
        raise ScorecardRejected("missing_section")
    attacks = list(linkage_expectation.get("attacks", ()))
    if not attacks:
        if linkage.get("note") not in BENIGN_NOTES:
            raise ScorecardRejected("missing_section")
        return
    if any(not isinstance(linkage.get(a), dict) for a in attacks):
        raise ScorecardRejected("missing_section")


def _evaluated(res) -> bool:
    """Every result record must say explicitly whether it was evaluated: a bool, nothing inferred."""
    if not isinstance(res, dict) or not isinstance(res.get("evaluated"), bool):
        raise ScorecardRejected("structure")
    return res["evaluated"]


def _check_results(name: str, tr: dict, expected: dict, found: list) -> None:
    """One rule for every result section (free text, linkage, trajectory, hash attack): an explicit
    `evaluated` bool; True needs its positive denominator; False was already restricted to the
    allowlisted not_applicable reasons by _scan_nested."""
    cols = set(expected.get("columns", ()))
    for res in (tr.get("free_text") or {}).values():
        if _evaluated(res) and res.get("status") != "withheld" and not _positive(res.get("n_values")):
            raise ScorecardRejected("zero_denominator")
    for key, res in (tr.get("linkage") or {}).items():
        if key == "note":
            if not isinstance(res, str):
                raise ScorecardRejected("structure")
            continue
        if _evaluated(res):
            if "n_targets_in_data" not in res:
                raise ScorecardRejected("structure")
            n = res["n_targets_in_data"]
            if n is None:
                # Only the kit's "every attacker column was removed" shape, and only when the release
                # provably lacks those columns (expected linkage names the adversary as column-less).
                absent = (expected.get("linkage") or {}).get("no_attack_columns", ())
                if res.get("qis_used") != [] or key not in absent:
                    raise ScorecardRejected("structure")
            elif not _positive(n):
                raise ScorecardRejected("zero_denominator")
    for user, res in (tr.get("trajectory_unicity") or {}).items():
        if _evaluated(res):
            if "n_users_tested" in res:
                if not _positive(res["n_users_tested"]):
                    raise ScorecardRejected("zero_denominator")
            elif res.get("note") == f"{user} removed: traces cannot be linked" and user not in cols:
                found.append({"table": name, "section": "trajectory_unicity", "key": user,
                              "code": "trajectory_user_removed"})
            else:
                raise ScorecardRejected("structure")
    for res in (tr.get("hash_attack") or {}).values():
        if _evaluated(res) and not _positive(res.get("n_hashes")):
            raise ScorecardRejected("zero_denominator")
    if "l_diversity" in tr:
        res = tr["l_diversity"]
        if _evaluated(res) and not _positive(res.get("n_classes")):
            raise ScorecardRejected("zero_denominator")
    synthetic = tr.get("synthetic")
    if synthetic is not None:
        if not isinstance(synthetic, dict):
            raise ScorecardRejected("structure")
        for part, denominator in (("dcr", "n_synthetic"), ("membership_inference", "n_each")):
            if part in synthetic and _evaluated(synthetic[part]) and not _positive(synthetic[part].get(denominator)):
                raise ScorecardRejected("zero_denominator")


def _check_released(name: str, tr: dict, expected: dict, found: list) -> None:
    for section in BASELINE_SECTIONS:
        if section not in tr:
            raise ScorecardRejected("missing_section")
    free_text = tr.get("free_text")
    if expected.get("free_text") and (
            not isinstance(free_text, dict) or any(c not in free_text for c in expected["free_text"])):
        raise ScorecardRejected("missing_section")
    _check_expected_linkage(tr, expected.get("linkage"))
    trajectories = tr.get("trajectory_unicity") if isinstance(tr.get("trajectory_unicity"), dict) else {}
    for user in expected.get("trajectories") or {}:
        if not isinstance(trajectories.get(user), dict):
            raise ScorecardRejected("missing_section")
    if not _int(tr.get("rows_original")) or not _int(tr.get("rows_protected")):
        raise ScorecardRejected("structure")
    if tr["rows_original"] <= 0 or tr["rows_protected"] <= 0:
        raise ScorecardRejected("zero_denominator")
    risks = tr.get("risks")
    if not isinstance(risks, dict) or not all(_num(v) for v in risks.values()):
        raise ScorecardRejected("structure")
    k = tr.get("k_anonymity")
    if not isinstance(k, dict):
        raise ScorecardRejected("structure")
    if "n" in k:
        if not _positive(k["n"]):
            raise ScorecardRejected("zero_denominator")
    elif not isinstance(k.get("note"), str):
        raise ScorecardRejected("structure")
    _check_k(tr, expected)
    _check_results(name, tr, expected, found)


K_RISK = "records with k<5"
NO_QI_NOTE = "no catalogued quasi-identifier kept"


def _check_k(tr: dict, expected: dict) -> None:
    """The k evaluation the kit must have run, from the caller's derivation (catalogued QIs the release
    keeps): QIs kept -> a k result over exactly those QIs, on every protected row, and its k<5 component;
    none kept -> exactly the kit's "no QI kept" note and no k component. A missing derivation is a fail."""
    qis = expected.get("quasi_identifiers")
    if not isinstance(qis, list) or not all(isinstance(c, str) for c in qis):
        raise ScorecardRejected("structure")
    k, risks = tr["k_anonymity"], tr["risks"]
    if not qis:
        if k != {"note": NO_QI_NOTE} or K_RISK in risks:
            raise ScorecardRejected("k_mismatch")
        return
    if "n" not in k:
        raise ScorecardRejected("not_evaluated")
    if not isinstance(k.get("qis"), list) or not all(isinstance(c, str) for c in k["qis"]) \
            or set(k["qis"]) != set(qis):
        raise ScorecardRejected("k_mismatch")
    if k["n"] != tr["rows_protected"]:
        raise ScorecardRejected("row_count_mismatch")
    share = k.get("share_below").get("k<5") if isinstance(k.get("share_below"), dict) else None
    if not _num(share) or not 0.0 <= share <= 1.0:
        raise ScorecardRejected("structure")
    if K_RISK not in risks:
        raise ScorecardRejected("missing_section")
    if risks[K_RISK] != share:
        raise ScorecardRejected("risk_mismatch")


def _check_table(name: str, tr: dict, expected: dict, found: list, *, rows_original: int,
                 rows_protected: int | None) -> dict:
    """`rows_original` / `rows_protected` are the adapter's own counts; `rows_protected` is None when the
    table is not in the release. The evaluator's status and counts must agree exactly: a released file
    never takes the withheld branch."""
    if not _name(name):
        raise ScorecardRejected("structure")
    _scan_nested(name, tr, expected, found)
    status = tr.get("status")
    if status == "error":
        raise ScorecardRejected("error_status")
    if status not in ("released", "withheld"):
        raise ScorecardRejected("structure")
    if status != ("withheld" if rows_protected is None else "released"):
        raise ScorecardRejected("status_mismatch")
    if not _int(tr.get("rows_original")) and status == "withheld":
        raise ScorecardRejected("structure")
    if status == "released":
        _check_released(name, tr, expected, found)
        if not tr["risks"]:  # the kit always scores at least "direct identifiers retained"
            raise ScorecardRejected("missing_section")
        if tr["rows_protected"] != rows_protected:
            raise ScorecardRejected("row_count_mismatch")
    if tr["rows_original"] != rows_original:
        raise ScorecardRejected("row_count_mismatch")
    return {"table": name, "status": status, "rows_original": int(tr["rows_original"]),
            "rows_protected": int(tr["rows_protected"]) if status == "released" else None}


def _row_counts(counts) -> dict:
    """A table -> row-count map from the adapter; anything else is a caller error, not a pass."""
    if not isinstance(counts, Mapping) or not all(
            _name(k) and _int(v) and v >= 0 for k, v in counts.items()):
        raise ScorecardRejected("structure")
    return dict(counts)


def validate_report(report: dict, *, scenario: str, required_tasks: Iterable[str],
                    tables: Mapping[str, int], released: Mapping[str, int],
                    expected_sections: dict | None = None) -> dict:
    """Return the allowlisted aggregate summary, or raise ScorecardRejected.

    `tables` (original table -> original rows) and `released` (table really in the release -> protected
    rows) are the adapter's own counts. The report must list exactly the original tables, mark exactly the
    released ones `released` with matching counts, and its `risk_components` must be exactly the released
    tables' risks: nothing the evaluator skipped or dropped passes as withheld or as an empty map.

    `expected_sections` (table -> {"free_text": [columns that must be evaluated], "linkage": bool})
    names the result sections this scenario requires beyond the baseline ones; the caller derives it
    from the kit (catalog, gold spans, identity data). Every released table's entry must carry
    "quasi_identifiers" (the catalogued QIs the release keeps): the k evaluation is checked against it and
    a released table without it is a fail (#110). Unavailable evaluations pass only with a BENIGN_REASONS
    reason, and are exported as `not_applicable` with their code."""
    tables, released = _row_counts(tables), _row_counts(released)
    if set(released) - set(tables):
        raise ScorecardRejected("unknown_table")
    if not released:
        raise ScorecardRejected("no_released_table")
    if not isinstance(report, dict):
        raise ScorecardRejected("structure")
    summary = report.get("summary")
    if not isinstance(summary, dict) or not all(_num(summary.get(k)) for k in ("privacy", "utility", "composite")):
        raise ScorecardRejected("structure")
    if _scenario_id(report) != scenario:
        raise ScorecardRejected("scenario")
    if not _name(report.get("dataset")) or not _name(scenario):
        raise ScorecardRejected("structure")
    rep_tables = report.get("tables")
    if not isinstance(rep_tables, dict):
        raise ScorecardRejected("structure")
    for name in tables:
        if name not in rep_tables:
            raise ScorecardRejected("missing_table")
    if set(rep_tables) - set(tables):
        raise ScorecardRejected("unknown_table")
    exported_tables, found = [], []
    expected_sections = expected_sections or {}
    for name, tr in rep_tables.items():
        if not isinstance(tr, dict):
            raise ScorecardRejected("structure")
        exported_tables.append(_check_table(name, tr, expected_sections.get(name, {}), found,
                                            rows_original=tables[name], rows_protected=released.get(name)))
    for item in found:
        if not (_name(item["table"]) and item["section"] in SECTIONS and _CODE.fullmatch(item["code"])
                and (item["key"] == "" or _KEY.fullmatch(item["key"]))):
            raise ScorecardRejected("structure")
    tasks = _check_tasks(report, list(required_tasks))
    risks = report.get("risk_components")
    if not isinstance(risks, dict) or not all(
            isinstance(k, str) and _RISK_KEY.fullmatch(k) and _num(v) for k, v in risks.items()):
        raise ScorecardRejected("structure")
    if not risks:
        raise ScorecardRejected("missing_section")
    # the kit builds risk_components as "<table>: <risk>" over the released tables; anything else is not it
    derived = {f"{name}: {k}": v for name in sorted(released) for k, v in rep_tables[name]["risks"].items()}
    if risks != derived:
        raise ScorecardRejected("risk_mismatch")
    return {
        "scenario": scenario,
        "dataset": report["dataset"],
        "privacy": float(summary["privacy"]),
        "utility": float(summary["utility"]),
        "composite": float(summary["composite"]),
        "tasks": sorted(tasks, key=lambda t: t["id"]),
        "risks": {k: float(v) for k, v in sorted(risks.items())},
        "tables": sorted(exported_tables, key=lambda t: t["table"]),
        "not_applicable": sorted(found, key=lambda i: (i["table"], i["section"], i["key"], i["code"])),
    }






