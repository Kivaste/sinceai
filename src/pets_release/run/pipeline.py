"""``run``: kit -> plan -> pseudonyms -> local suppression -> contract -> gated, signed, atomic release.

Steps: load the scenario's dataset (01's ``Kit``, dtype=str) -> validate the hand plan (09) -> ``ladders.apply``
(07) with release-scope keyed pseudonyms (06) -> local suppression of below-k persons (policy field, here) ->
contract (10) -> producer context (``context.producer_context``, the same function ``verify --full`` uses) ->
``write_release`` (16: gate, manifest, signature, self-scan, atomic rename, ``<out>.scoring/``).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from pets_release.checks import text as text_checks
from pets_release.contract import generate as generate_contract
from pets_release.ladders import apply as apply_plan
from pets_release.manifest import canonical_bytes, release_scope_id
from pets_release.policy import get_policy, hand_plan, validate_plan
from pets_release.pseudonym import MasterKey
from pets_release.run.context import DEFAULT_RECIPIENT, SCENARIO_SPEC, producer_context, token_keys
from pets_release.run.narrative import build_narrative
from pets_release.run.suppress import apply_suppression
from pets_release.writer import Candidate, ProtectedTable, scoring_dir, write_release

SUPPRESSION_REPORT = "suppression_report.json"
PERSON_K_REPORT = "person_k_report.json"


class RunError(Exception):
    """Content-free usage/unknown-state error (exit 2)."""


class RunRefused(Exception):
    """Content-free refusal before the writer (exit 1)."""


@dataclass(frozen=True)
class RunOutcome:
    status: str
    out: Path
    scoring: Path
    reasons: tuple
    suppression: dict


def _sorted_like_writer(df: pd.DataFrame, final: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Order rows exactly as the writer writes them (sorted (row tuple, source key)); its sort is then a no-op."""
    rows = list(df.itertuples(index=False, name=None))
    order = sorted(range(len(df)), key=lambda i: (rows[i], final[i]))
    return df.iloc[order].reset_index(drop=True), [final[i] for i in order]


def run_release(*, kit, scenario: dict, created: str, key_text: str, out, plan_name: str,
                tool_revision: str) -> RunOutcome:
    scenario_id = scenario.get("id")
    if scenario_id == "CS-S1" and plan_name == "hand":  # ticket 23: CS-S1 glue
        from pets_release.cs_s1.release import run_cs_s1

        return run_cs_s1(kit=kit, scenario=scenario, created=created, key_text=key_text, out=out,
                         tool_revision=tool_revision)
    if scenario_id not in SCENARIO_SPEC:
        raise RunError("run supports only HEALTH-S1 in this build")
    if plan_name != "hand":
        raise RunError("only --plan hand is supported in this build")
    policy = get_policy(scenario_id)
    if scenario.get("dataset") != policy.dataset:
        raise RunError("scenario dataset differs from the policy dataset")
    out = Path(out).absolute()
    if out.exists() or scoring_dir(out).exists():
        raise RunError("output folder or its scoring folder already exists")
    plan = hand_plan(scenario_id)
    validate_plan(plan, policy)

    source = kit.load_dataset(policy.dataset)
    inputs = kit.input_digests(policy.dataset)
    master = MasterKey.from_text(key_text)
    recipient = DEFAULT_RECIPIENT
    rsid = release_scope_id(scenario=scenario_id, recipient=recipient, inputs=inputs, tool_revision=tool_revision)

    released = apply_plan(plan, source, token_keys(master, rsid, recipient))
    spec = SCENARIO_SPEC[scenario_id]
    finals = {}
    for stem, df in released.items():
        rk = spec["record_keys"][stem]
        finals[stem] = source[stem].loc[df.index, rk].tolist()  # apply keeps the source index
        released[stem] = df.reset_index(drop=True).astype(str)
    contract = generate_contract(policy, plan)

    base = producer_context(scenario_id=scenario_id, policy=policy, source=source, master=master, scope_id=rsid,
                            recipient=recipient, contract=contract, released=None)
    released, finals, suppressed, sup = apply_suppression(released, finals, policy=policy, contract=contract,
                                                          base_ctx=base)
    if not sup.get("withinBound", True):
        sc = scoring_dir(out)
        sc.mkdir(parents=True)
        (sc / "refusal_report.json").write_bytes(canonical_bytes(
            {"status": "refused", "scenario": scenario_id, "reasons": ["suppression:share-above-max"],
             "suppression": sup}))
        raise RunRefused("suppression share above the policy bound")

    tables = []
    ordered = {}
    for stem in sorted(released):
        df, fin = _sorted_like_writer(released[stem], finals[stem])
        ordered[stem] = df
        tables.append(ProtectedTable(name=f"{stem}.csv", frame=df, final=tuple(fin),
                                     suppressed=frozenset(suppressed.get(stem, set()))))
        finals[stem] = fin
    gate_ctx = producer_context(scenario_id=scenario_id, policy=policy, source=source, master=master,
                                scope_id=rsid, recipient=recipient, contract=contract, released=ordered)
    for stem, rm in gate_ctx["rowmaps"].items():  # self-check: token inversion == lineage
        if rm["original_record_id"].tolist() != finals[stem]:
            raise RunError("row-map reconstruction disagrees with lineage")

    narrative = build_narrative(policy=policy, plan=plan, scenario_ids=[s["id"] for s in kit.scenarios()],
                                suppression=sup, k=contract["k"])
    cand = Candidate(
        scenario=scenario_id, recipient=recipient, tables=tuple(tables), contract=contract,
        tool_revision=tool_revision, created=created, narrative=narrative,
        # keep/geo rungs carry the gate's `text` form, so text.health runs and needs its lexicon bound
        lexicon_digests={text_checks.LEXICON_NAME: text_checks.lexicon_digest()},
        scoring_files={SUPPRESSION_REPORT: canonical_bytes(sup),
                       PERSON_K_REPORT: canonical_bytes(sup.get("personKAfter", {}))},
    )
    res = write_release(cand, out, master, kit, context=gate_ctx)
    return RunOutcome(res.status, res.out, res.scoring, res.reasons, sup)
