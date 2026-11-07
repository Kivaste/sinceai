"""``run --scenario CS-S1 --plan hand`` (ticket 23), called from ``pets_release.run.pipeline``.

kit -> ``prepare`` (turn_id decision, pseudonyms, hour timestamps, redaction with the controller
gazetteer) -> contract -> producer context (``run.context``, the same function ``verify --full`` uses) ->
measurements (purpose checks before/after, CS-U5 twice on the fallback; held-out redaction recall) ->
``write_release`` -> local spot-check sheet in ``<out>.scoring/`` (raw text: never in the repo).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from pets_release.checks import text as text_checks
from pets_release.contract import generate as generate_contract
from pets_release.cs_s1 import measure as cs_measure
from pets_release.cs_s1.prepare import SCENARIO, prepare
from pets_release.manifest import canonical_bytes, not_measured, release_scope_id
from pets_release.policy import get_policy
from pets_release.pseudonym import MasterKey
from pets_release.run.context import DEFAULT_RECIPIENT, SCENARIO_SPEC, producer_context, token_keys
from pets_release.run.narrative import build_narrative
from pets_release.writer import Candidate, ProtectedTable, scoring_dir, write_release

UTILITY_REPORT = "utility_report.json"
REDACTION_REPORT = "redaction_report.json"
TURN_ID_REPORT = "turn_id_assessment.json"
SPOT_CHECK = "spot_check.csv"
_HEALTH_ONLY_RISKS = {"scorecard-renamed-qi", "linkage-attackers", "attribute-inference"}


def _sorted_like_writer(df: pd.DataFrame, final: list[str]):
    rows = list(df.itertuples(index=False, name=None))
    order = sorted(range(len(df)), key=lambda i: (rows[i], final[i]))
    return df.iloc[order].reset_index(drop=True), [final[i] for i in order]


def run_cs_s1(*, kit, scenario: dict, created: str, key_text: str, out, tool_revision: str):
    from pets_release.run.pipeline import RunError, RunOutcome

    policy = get_policy(SCENARIO)
    if scenario.get("dataset") != policy.dataset:
        raise RunError("scenario dataset differs from the policy dataset")
    out = Path(out).absolute()
    if out.exists() or scoring_dir(out).exists():
        raise RunError("output folder or its scoring folder already exists")
    source = kit.load_dataset(policy.dataset)
    inputs = kit.input_digests(policy.dataset)
    master = MasterKey.from_text(key_text)
    recipient = DEFAULT_RECIPIENT
    rsid = release_scope_id(scenario=SCENARIO, recipient=recipient, inputs=inputs, tool_revision=tool_revision)

    prep = prepare(source, token_keys(master, rsid, recipient))
    contract = generate_contract(policy, prep.plan)
    rk = SCENARIO_SPEC[SCENARIO]["record_keys"]
    ordered, finals, tables = {}, {}, []
    for stem in sorted(prep.tables):
        df = prep.tables[stem]
        fin = source[stem].loc[df.index, rk[stem]].tolist()  # apply keeps the source index
        df, fin = _sorted_like_writer(df.reset_index(drop=True).astype(str), fin)
        ordered[stem], finals[stem] = df, fin
        tables.append(ProtectedTable(name=f"{stem}.csv", frame=df, final=tuple(fin), suppressed=frozenset()))
    gate_ctx = producer_context(scenario_id=SCENARIO, policy=policy, source=source, master=master, scope_id=rsid,
                                recipient=recipient, contract=contract, released=ordered)
    for stem, rm in gate_ctx["rowmaps"].items():  # self-check: token inversion == lineage
        if rm["original_record_id"].tolist() != finals[stem]:
            raise RunError("row-map reconstruction disagrees with lineage")

    turns_map = None
    if not prep.turn_id.kept:  # lineage row map for the separately labelled adapted CS-U5 score
        turns_map = pd.DataFrame({"protected_row": [str(i) for i in range(len(finals["turns"]))],
                                  "original_record_id": finals["turns"]}, dtype=str)
    util_block, util = cs_measure.utility(SCENARIO, source, ordered, turns_map, root=kit.root)
    red = cs_measure.redaction(kit.root, prep.spans)

    narrative = build_narrative(policy=policy, plan=prep.plan, scenario_ids=[s["id"] for s in kit.scenarios()],
                                suppression={}, k=contract.get("k"))
    narrative["fieldJustifications"] = sorted(
        [prep.turn_id.justification if (j["table"], j["column"]) == ("turns", "turn_id") else j
         for j in narrative["fieldJustifications"]], key=lambda j: (j["table"], j["column"]))
    narrative["measured"] = dict(narrative["measured"], utility=util_block, redaction=red["measured"],
                                 privacy=not_measured("scorecard privacy components: measurer (ticket 22)"),
                                 baselines=not_measured("published baselines: measurer (ticket 22)"))
    narrative["residualRisks"] = sorted(
        [r for r in narrative["residualRisks"] if r["risk"] not in _HEALTH_ONLY_RISKS] + red["risks"],
        key=lambda r: r["risk"])
    narrative["sacrifices"] = [dict(s, before=util.get(s["check"], {}).get("before"),
                                    after=util.get(s["check"], {}).get("after")) for s in narrative["sacrifices"]]

    cand = Candidate(
        scenario=SCENARIO, recipient=recipient, tables=tuple(tables), contract=contract,
        tool_revision=tool_revision, created=created, narrative=narrative,
        lexicon_digests={text_checks.LEXICON_NAME: text_checks.lexicon_digest()},
        scoring_files={UTILITY_REPORT: canonical_bytes(util), REDACTION_REPORT: canonical_bytes(red["report"]),
                       TURN_ID_REPORT: canonical_bytes(prep.turn_id.assessment)},
    )
    res = write_release(cand, out, master, kit, context=gate_ctx)
    if res.status != "released" and res.scoring.is_dir():  # aggregates stay available for diagnosis
        for name, body in cand.scoring_files.items():
            if not (res.scoring / name).exists():
                (res.scoring / name).write_bytes(body)
    if red["frame"] is not None and res.scoring.is_dir():
        from pets_release.redaction_eval import export_spot_check

        export_spot_check(red["frame"], red["pred"], res.scoring / SPOT_CHECK, n=200, ids=list(red["held"]) or None)
    return RunOutcome(res.status, res.out, res.scoring, res.reasons, {})
