"""Manifest narrative sections built from the policy, the final plan and the suppression report.

Schema names, rung IDs, policy reasons and aggregate counts only; never a row value. ``measured.*`` is the
schema's ``not_measured`` value until the measurer is wired (ticket 22).
"""
from __future__ import annotations

from pets_release.ladders import WITHHELD, output_column
from pets_release.manifest import not_measured

_RECORD_KEYS = {("ed_visits", "visit_id"), ("lab_results", "lab_id"), ("lab_results", "visit_id"),
                ("clinical_notes", "note_id"), ("clinical_notes", "visit_id"),
                ("published_weekly_stats", "stat_id")}


def _role(policy, table, column) -> str:
    key = (table, column)
    fam = policy.floors[key].family
    if key in policy.direct_identifiers:
        return "direct_identifier"
    if key in _RECORD_KEYS:
        return "record_key"
    if any((q["table"], q["column"]) == key for q in policy.qi):
        return "quasi_identifier"
    if fam == "text":
        return "free_text"
    if fam == "identifier":
        return "technical_identifier"
    if fam in ("icd10", "numeric") or table == "lab_results":
        return "sensitive_attribute"
    return "non_sensitive"


def _pet(entry) -> tuple[str, dict]:
    rung, params = entry["rung"], entry["params"]
    if rung == WITHHELD:
        return "withholding", {}
    if rung == "id.pseudonym":
        return "keyed_pseudonym", {"scope": "release", "label": params.get("label", "RECORD_KEY")}
    if rung == "geo.topn":
        return "top_n_grouping", {"topN": params["n"]}
    if rung == "num.round":
        return "rounding", {"rung": rung}
    if rung == "num.bin":
        return "binning", {"rung": rung}
    if rung in ("keep", "num.exact", "geo.full", "icd.full", "ts.exact"):
        return "none", {}
    return "generalisation", {"rung": rung}


def build_narrative(*, policy, plan, scenario_ids, suppression: dict, k: int, purpose=None, search=None,
                    rung_steps=()) -> dict:
    """``purpose``: the accepted ``run.purpose.PurposeResult``; fills ``measured.utility`` and the sacrifices'
    before/after scores (None leaves them not measured / null).
    ``search`` (ticket 25): {"justifications", "summary", "sacrifices"} from ``run.justify`` and the search
    result; None for the hand plan. Its sacrifice scores are used only when no ``purpose`` result is given.
    ``rung_steps``: adopted enumerated rung sacrifices (``run.pipeline.rung_step``), each recorded as
    ``rungStep`` on its check's sacrifice entry."""
    by_key = sorted(plan, key=lambda e: (e["table"], e["column"]))
    inventory = [{"dataset": policy.dataset, "table": e["table"], "column": e["column"],
                  "role": _role(policy, e["table"], e["column"]),
                  "subtype": policy.floors[(e["table"], e["column"])].family,
                  "evidence": [f"scenario policy {policy.scenario}"]} for e in by_key]
    pets = []
    for e in by_key:
        pet, params = _pet(e)
        pets.append({"table": e["table"], "column": e["column"], "pet": pet, "params": params})
    if suppression.get("method") == "local_suppression":
        person = ("ed_visits", "patient_hetu")
        pets.append({"table": person[0], "column": person[1], "pet": "local_suppression",
                     "params": {"k": suppression["k"], "maxShare": suppression["maxShare"],
                                "unitsSuppressed": suppression["unitsSuppressed"],
                                "share": suppression["share"]}})
        pets.sort(key=lambda p: (p["table"], p["column"], p["pet"]))
    fj = []
    for e in by_key:
        released = e["rung"] != WITHHELD
        fj.append({"table": e["table"], "column": e["column"],
                   "outputColumn": output_column(e) if released else None,
                   "decision": "released" if released else "withheld",
                   "rung": e["rung"], "floor": e["floor"], "reason": e["reason"][:500], "source": e["source"]})
    if search is not None:
        fj = list(search["justifications"])
    pending = "not measured yet: the measurer is wired in the story-kit ticket"
    measured = {"utility": not_measured(pending), "privacy": not_measured(pending),
                "search": (dict(search["summary"]) if search is not None
                           else not_measured("hand-picked plan; no search run")),
                "baselines": not_measured(pending), "redaction": not_measured("no free text released")}
    scored = {}
    if purpose is not None:
        from pets_release.run.purpose import measured_utility, scores

        measured["utility"] = measured_utility(purpose)
        scored = scores(purpose)
    risks = []
    for n in policy.residual_notes:
        rate = not_measured(n["note"][:500]) if n["status"] == "open" else {"status": "not_applicable",
                                                                            "reason": "no free text released"}
        risks.append({"risk": n["id"], "kind": "note", "label": None, "rate": rate, "description": n["note"][:500]})
    risks += [
        {"risk": "recipient-verify-tamper-limitation", "kind": "tamper_limitation", "label": None,
         "rate": {"status": "not_applicable", "reason": "structural property of recipient-mode verify"},
         "description": "file digests detect accidental change only; only verify --full checks the HMAC signature"},
        {"risk": "scorecard-renamed-qi", "kind": "scorecard_defect", "label": None,
         "rate": not_measured("structural; disclosed per decision D22"),
         "description": "the kit scorecard does not count the renamed age_band column as a quasi-identifier; "
                        "our per-person k over every released quasi-identifier is authoritative"},
        {"risk": "linkage-attackers", "kind": "linkage", "label": None, "rate": not_measured(pending),
         "description": "linkage rate under both attacker personas"},
        {"risk": "attribute-inference", "kind": "attribute_inference", "label": None,
         "rate": not_measured(pending), "description": "attribute inference from released quasi-identifiers"},
    ]
    risks.sort(key=lambda r: r["risk"])
    if not scored:
        scored = {s["check"]: (s["score_before"], s["score_after"]) for s in (search or {}).get("sacrifices", [])}
    sacrifices = sorted(({"check": s["check"], "floor": s["floor_score"],
                          "before": scored.get(s["check"], (None, None))[0],
                          "after": scored.get(s["check"], (None, None))[1],
                          "reason": s["reason"][:500]} for s in policy.sacrifices), key=lambda s: s["check"])
    by_check = {s["check"]: s for s in sacrifices}
    for st in rung_steps:
        entry = by_check[st["check"]]  # policy validation: a rung sacrifice's check has a sacrifice entry
        if "rungStep" in entry:
            raise ValueError("two rung steps for one sacrifice")
        entry["rungStep"] = {k: v for k, v in st.items() if k != "check"}
    checks = ", ".join(policy.purpose_checks)
    fit = [{"scenario": policy.scenario,
            "reason": f"built and gated for {policy.scenario} purpose checks {checks}; per-person k >= {k}"}]
    not_fit = [{"scenario": s, "reason": "different recipient or purpose; not gated for it"}
               for s in sorted(scenario_ids) if s != policy.scenario]
    return {"inventory": inventory, "pets": pets, "fieldJustifications": fj, "measured": measured,
            "residualRisks": risks, "sacrifices": sacrifices, "fitFor": fit, "notFitFor": not_fit}
