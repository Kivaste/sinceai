"""Per-person k on two QI sets, and the withheld catalogued QIs with their justifications (#146, decision D58).

The kit's scorecard judges k on every catalogued quasi-identifier a release keeps; the scenario's suggested QIs are
a design target. The manifest's ``measured.kSets`` therefore reports both:

  (a) ``scenario``: the scenario's suggested QIs (``SCENARIO_QI``), in the forms the release actually carries: the
      ``contract.qi`` rows whose source column is one of them (a withheld one drops out);
  (b) ``keptCatalogued``: every catalogued QI the release keeps, i.e. all of ``contract.qi``. Every released
      catalogued QI must be in it, else the set is not measured.

Each measured set gives per-person k (persons, unidentified units, min, median, below-k count and share) before
local suppression (the plan applied) and on the released tables (after suppression), through the production
``person_k_values`` rule with the set's QIs as the contract's QIs. Next to the sets: every catalogued QI
(``policy.qi`` plus the kit data dictionary's QIs in ``KIT_DICTIONARY_QI``) the release withholds, with its
``fieldJustifications`` reason. A catalogued QI without a justification makes the whole section not measured.

Fail closed: a set that cannot be computed is ``not_measured`` with a content-free reason, never a pass; ``verify
--full`` re-measures the section with this module and fails when it differs or is not measured. Aggregates only.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from pets_release.ladders import WITHHELD, output_column
from pets_release.manifest import not_measured

SCENARIO = "scenario"
KEPT = "keptCatalogued"
SOURCE = ("producer.person-k rule (person_k_values) over each set's QIs; beforeSuppression: the plan applied, "
          "before local suppression; released: the published tables")

# The scenario's suggested QIs (kit scenarios.json, suggested_privacy_targets: "k>=5 on (age band, sex,
# municipality, arrival week)"), as source columns of the person table.
SCENARIO_QI = {
    "HEALTH-S1": frozenset({("ed_visits", "date_of_birth"), ("ed_visits", "sex"), ("ed_visits", "municipality"),
                            ("ed_visits", "arrival_ts")}),
}

# Columns the kit data dictionary (docs/DATA_DICTIONARY.md) gives the role quasi_identifier that the policy's QI list
# does not name: every one has the floor ``withheld``, so it can only appear in the withheld list.
KIT_DICTIONARY_QI = {
    "HEALTH-S1": frozenset({("ed_visits", "postcode"), ("clinical_notes", "written_ts"),
                            ("clinical_notes", "language"), ("published_weekly_stats", "week"),
                            ("published_weekly_stats", "municipality"), ("published_weekly_stats", "age_band"),
                            ("published_weekly_stats", "sex")}),
}


class KSetsError(Exception):
    """Content-free: the k-set section cannot be assembled."""


def catalogued_qis(policy) -> list[tuple[str, str]]:
    return sorted({(q["table"], q["column"]) for q in policy.qi} | set(KIT_DICTIONARY_QI.get(policy.scenario, ())))


def _not_measured_set(name: str, reason: str) -> dict:
    return {"set": name, **not_measured(reason)}


def _summary(res, k: int) -> dict:
    vals = sorted(res.per_person.values())
    persons = len(vals) + res.unidentified
    if persons <= 0:
        raise KSetsError("no persons")
    below = sum(1 for v in vals if v < k) + res.unidentified
    return {"persons": persons, "unidentifiedUnits": res.unidentified,
            "minK": vals[0] if vals else None, "medianK": vals[len(vals) // 2] if vals else None,
            "belowK": below, "belowKShare": round(below / persons, 6)}


def _qi_sort(rows) -> list[dict]:
    return sorted((dict(q) for q in rows), key=lambda q: (q["table"], q["column"]))


def measure_sets(policy, plan, contract, *, source, master, scope_id, recipient) -> list[dict]:
    """The two set records for ``plan`` (the run's own ``applied`` and local suppression, re-done here). Each is
    measured or ``not_measured`` with a reason; never raises for a computation failure."""
    from pets_release.run.context import producer_context
    from pets_release.run.pipeline import applied
    from pets_release.run.suppress import apply_suppression, person_k_of

    k = (contract or {}).get("k")
    if not isinstance(k, int) or isinstance(k, bool) or k < 2:
        return [_not_measured_set(n, "the scenario has no k target") for n in (SCENARIO, KEPT)]
    qi = _qi_sort(contract.get("qi") or [])
    listed = {(q["table"], q["column"]) for q in qi}
    catalogued = set(catalogued_qis(policy))
    kept_ok = all((e["table"], output_column(e)) in listed for e in plan
                  if e["rung"] != WITHHELD and (e["table"], e["column"]) in catalogued)
    scen = SCENARIO_QI.get(policy.scenario)
    wanted = {SCENARIO: None if scen is None else [q for q in qi if (q["table"], q["derived_from"]) in scen],
              KEPT: qi if kept_ok else None}
    try:
        pre, pre_finals = applied(plan, policy=policy, source=source, master=master, scope_id=scope_id,
                                  recipient=recipient)
        base = producer_context(scenario_id=policy.scenario, policy=policy, source=source, master=master,
                                scope_id=scope_id, recipient=recipient, contract=contract, released=None)
        post, post_finals, _, _ = apply_suppression(pre, pre_finals, policy=policy, contract=contract, base_ctx=base)
        out = []
        with tempfile.TemporaryDirectory(prefix="pets-ksets-") as td:
            tmp = Path(td)
            for name in (SCENARIO, KEPT):
                rows = wanted[name]
                if rows is None:
                    out.append(_not_measured_set(name, "the scenario names no quasi-identifier set in this build"
                                                 if name == SCENARIO else
                                                 "a kept catalogued quasi-identifier is outside contract qi"))
                    continue
                sub = {**contract, "qi": rows}
                before = _summary(person_k_of(pre, pre_finals, sub, base, tmp), k)
                after = _summary(person_k_of(post, post_finals, sub, base, tmp), k)
                out.append({"set": name, "status": "measured", "qi": rows, "beforeSuppression": before,
                            "released": after})
        return out
    except Exception:  # noqa: BLE001 - fail closed, content-free (a message could carry values)
        return [_not_measured_set(n, "per-person k could not be computed") for n in (SCENARIO, KEPT)]


def withheld_catalogued(policy, field_justifications) -> list[dict]:
    """Every catalogued QI the release withholds, with its justification. Raises KSetsError when a catalogued QI
    has no field justification."""
    fj = {(f["table"], f["column"]): f for f in field_justifications}
    out = []
    for key in catalogued_qis(policy):
        f = fj.get(key)
        if f is None:
            raise KSetsError("a catalogued quasi-identifier has no field justification")
        if f["decision"] == "withheld":
            out.append({"table": key[0], "column": key[1], "reason": f["reason"]})
    return out


def k_sets_block(policy, contract, field_justifications, sets) -> dict:
    """The manifest's ``measured.kSets`` section (or ``not_measured``)."""
    if sets is None:
        return not_measured("k sets not measured for this release")
    k = (contract or {}).get("k")
    if not isinstance(k, int) or isinstance(k, bool) or k < 2:
        return not_measured("the scenario has no k target")
    try:
        withheld = withheld_catalogued(policy, field_justifications)
    except KSetsError as e:
        return not_measured(str(e))
    return {"status": "measured", "source": SOURCE, "k": k, "sets": [dict(s) for s in sets], "withheld": withheld}


def k_sets_problems(manifest: dict, source: dict, master_key) -> list[str]:
    """``verify --full``: re-measure ``measured.kSets`` from the manifest's rungs (rebuilt with the hand plan's params,
    as the search does) and the kit; it must equal the signed section and be measured. Content-free lines."""
    from pets_release.minimiser import rebuild_plan
    from pets_release.minimiser.kit import params_from_plan
    from pets_release.policy import get_policy, hand_plan, validate_plan

    signed = manifest["measured"]["kSets"]
    contract = manifest["contract"]
    if "k" not in contract:
        return [] if signed.get("status") == "not_measured" else ["measured.kSets: measured without a k target"]
    try:
        scenario = manifest["release"]["scenario"]
        policy = get_policy(scenario)
        fields = {(f["table"], f["column"]): (f["rung"], f["floor"]) for f in manifest["fieldJustifications"]}
        plan = rebuild_plan(policy, params_from_plan(hand_plan(scenario)), fields)
        validate_plan(plan, policy)
    except Exception:  # noqa: BLE001 - unknown state fails closed, content-free
        return ["measured.kSets: not reproducible (plan cannot be rebuilt from the manifest's rungs)"]
    sets = measure_sets(policy, plan, contract, source=source, master=master_key,
                        scope_id=manifest["release"]["releaseScopeId"], recipient=manifest["release"]["recipient"])
    fresh = k_sets_block(policy, contract, manifest["fieldJustifications"], sets)
    out = []
    if fresh != signed:
        out.append("measured.kSets: re-measure differs from the manifest")
    if signed.get("status") != "measured":
        out.append("measured.kSets: not measured")
    else:
        out += [f"measured.kSets: {s['set']}: not measured" for s in signed["sets"] if s["status"] != "measured"]
    return out
