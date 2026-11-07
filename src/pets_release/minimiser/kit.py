"""Kit glue for the minimiser: purpose checks through ticket 08's adapter and per-scenario k specs.

``KSPECS`` gives ticket 11's per-person-k context (person column, record keys, joins to the person table) by
scenario, schema names only. ``params_from_plan`` takes rung parameters (e.g. the age reference column)
from the hand-picked plan, so the search and the walking skeleton parameterise rungs the same way.
"""

from __future__ import annotations

from pets_release.ladders import LADDERS

from .readsets import KIT_READ_SETS

KSPECS = {
    "HEALTH-S1": {
        "person": {"table": "ed_visits", "column": "patient_hetu"},
        "record_keys": {"ed_visits": "visit_id", "lab_results": "lab_id"},
        "joins": [{"table": "lab_results", "column": "visit_id", "ref_table": "ed_visits", "ref_column": "visit_id"}],
    },
}


def kit_purpose_check(task_id, original, protected):
    """One kit purpose check. Module-level, so a spawned search worker (#127) can unpickle it."""
    from pets_release import kiteval

    return kiteval.purpose_check(task_id, original, protected)


def kit_purpose(scenario_id: str, root):
    """(purpose, purpose_all) callables backed by ``pets_release.kiteval`` (the only pets_eval importer)."""
    from pets_release import kiteval

    def purpose_all(original, protected):
        return kiteval.purpose_checks(scenario_id, original, protected, root=root)

    return kit_purpose_check, purpose_all


def params_from_plan(plan: list) -> dict:
    """{(table, column): {rung: params}}: a hand-plan entry's params apply to every rung of its ladder that
    takes the same parameter kind (age bands share ``ref_column``/``output``; others only their own rung)."""
    out: dict = {}
    for e in plan:
        if not e["params"]:
            continue
        key = (e["table"], e["column"])
        rungs = [e["rung"]]
        if e["rung"] in LADDERS["age"]:
            rungs = [r for r in LADDERS["age"] if r != "withheld"]
        for r in rungs:
            out.setdefault(key, {})[r] = dict(e["params"])
    return out


def search_options(scenario_id: str, root, hand_plan: list) -> dict:
    """Keyword arguments for ``search`` on a kit scenario."""
    purpose, purpose_all = kit_purpose(scenario_id, root)
    return {"purpose": purpose, "purpose_all": purpose_all, "kspec": KSPECS.get(scenario_id),
            "read_sets": KIT_READ_SETS, "params": params_from_plan(hand_plan)}
