"""``run``: kit -> plan -> pseudonyms -> local suppression -> contract -> gated, signed, atomic release.

Steps: load the scenario's dataset (01's ``Kit``, dtype=str) -> validate the hand plan (09) -> ``ladders.apply``
(07) with release-scope keyed pseudonyms (06) -> local suppression of below-k persons (policy field, here) ->
contract (10) -> full re-check of every purpose check (``run.purpose``; failing refuses, scores go in the manifest) -> producer context (``context.producer_context``, the same function ``verify --full`` uses) ->
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
from pets_release.minimiser import LOG_KEYS, MinimiserRefused, rebuild_plan, search
from pets_release.minimiser.kit import params_from_plan, search_options
from pets_release.policy import get_policy, hand_plan, validate_plan
from pets_release.pseudonym import MasterKey
from pets_release.recipient import RecipientError, validate_recipient_id
from pets_release.run.context import DEFAULT_RECIPIENT, SCENARIO_SPEC, producer_context, token_keys
from pets_release.run.justify import JustificationError, justify, search_summary
from pets_release.run.ksets import measure_sets
from pets_release.run.narrative import build_narrative
from pets_release.run.purpose import evaluate as evaluate_purpose
from pets_release.run.suppress import apply_suppression
from pets_release.writer import Candidate, ProtectedTable, scoring_dir, write_release

SUPPRESSION_REPORT = "suppression_report.json"
PERSON_K_REPORT = "person_k_report.json"
SEARCH_LOG = "search_log.jsonl"


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


def search_log_bytes(log: list) -> bytes:
    """The SearchLogEntry JSONL (canonical JSON per line, LF), exact keys or nothing."""
    lines = []
    for e in log:
        if set(e) != LOG_KEYS:
            raise RunError("search log entry has unexpected keys")
        lines.append(canonical_bytes(e).decode("utf-8"))
    return ("\n".join(lines) + "\n").encode("utf-8")


def check_search_privacy(final, policy) -> None:
    """Fail closed on the search's final privacy re-check (ticket 24's ``final``).

    Releasable only when ``privacy_status`` is ``pass`` and ``privacy_targets`` lists exactly the policy's
    declared targets (by id and kind), each ``pass``; or ``not_applicable`` with no declared target and an
    empty list. Anything else not ``pass`` refuses (RunRefused); a malformed or self-contradicting result
    (including ``not_applicable`` with a non-empty target list) is an unknown state (RunError)."""
    if not isinstance(final, dict) or "privacy_status" not in final or "privacy_targets" not in final:
        raise RunError("search result has no privacy re-check")
    status, targets = final["privacy_status"], final["privacy_targets"]
    if not isinstance(targets, list) or not all(isinstance(t, dict) for t in targets):
        raise RunError("search privacy targets malformed")
    declared = sorted((str(t.get("id")), str(t.get("kind"))) for t in policy.privacy_targets)
    if status == "not_applicable":
        if targets:
            raise RunError("search privacy re-check not applicable yet lists targets")
        if declared:
            raise RunRefused("search privacy re-check not applicable although the policy declares targets")
        return
    if status != "pass":
        raise RunRefused(f"search privacy re-check: {status}")
    got = sorted((str(t.get("id")), str(t.get("kind"))) for t in targets)
    if not declared or got != declared or any(t.get("status") != "pass" for t in targets):
        raise RunError("search privacy re-check contradicts the policy targets")


def _search(scenario_id, policy, source, keys, kit, out: Path, workers: int = 1):
    """The bounded search (ticket 24) on the full source; a refusal writes its report and log, then raises.
    ``workers`` (#127) only changes how candidates are scored, never the result; it is recorded nowhere."""
    try:
        return search(policy, source, keys, **search_options(scenario_id, kit.root, hand_plan(scenario_id)),
                      workers=workers)
    except MinimiserRefused as e:
        sc = scoring_dir(out)
        sc.mkdir(parents=True)
        (sc / SEARCH_LOG).write_bytes(search_log_bytes(e.log))
        (sc / "refusal_report.json").write_bytes(canonical_bytes(
            {"status": "refused", "scenario": scenario_id, "reasons": ["search:no-acceptable-plan"],
             "search": {k: e.stats[k] for k in sorted(e.stats)}}))
        raise RunRefused("search found no acceptable plan") from None


def _refuse(out: Path, report: dict) -> None:
    sc = scoring_dir(out)
    sc.mkdir(parents=True)
    (sc / "refusal_report.json").write_bytes(canonical_bytes(report))


_AT_FROM = ("unitsBefore", "unitsSuppressed", "share", "maxShare", "withinBound")


def _within_bound(out: Path, scenario_id: str, sup: dict) -> bool:
    """The suppression report's ``withinBound``; a missing or non-bool value refuses (fail closed, #111)."""
    wb = sup.get("withinBound")
    if type(wb) is not bool:
        _refuse(out, {"status": "refused", "scenario": scenario_id, "reasons": ["suppression:within-bound-missing"],
                      "suppression": sup})
        raise RunRefused("suppression report has no within-bound result")
    return wb


def applied(plan, *, policy, source, master, scope_id, recipient):
    """Plan -> (released, finals) before local suppression: apply with release-scope pseudonyms; ``finals`` are the
    source record keys per released row. Used by ``protect`` and the k-set measure (#146)."""
    released = apply_plan(plan, source, token_keys(master, scope_id, recipient))
    spec = SCENARIO_SPEC[policy.scenario]
    finals = {}
    for stem, df in released.items():
        rk = spec["record_keys"][stem]
        finals[stem] = source[stem].loc[df.index, rk].tolist()  # apply keeps the source index
        released[stem] = df.reset_index(drop=True).astype(str)
    return released, finals


def protect(plan, *, policy, source, master, scope_id, recipient):
    """Plan -> (released, finals, suppressed, suppression report, contract): apply with release-scope pseudonyms,
    contract, local suppression. One function for ``run`` and the ``verify --full`` re-measure of a rung step."""
    released, finals = applied(plan, policy=policy, source=source, master=master, scope_id=scope_id,
                               recipient=recipient)
    contract = generate_contract(policy, plan)
    base = producer_context(scenario_id=policy.scenario, policy=policy, source=source, master=master,
                            scope_id=scope_id, recipient=recipient, contract=contract, released=None)
    released, finals, suppressed, sup = apply_suppression(released, finals, policy=policy, contract=contract,
                                                          base_ctx=base)
    return released, finals, suppressed, sup, contract


def k_at_from(sup: dict) -> dict:
    """The measured k result that justifies a rung sacrifice: suppression needed at `from` beyond the budget.
    Fails closed (RunError) when any figure is missing or does not show the budget exceeded."""
    if any(k not in sup for k in _AT_FROM):
        raise RunError("rung sacrifice: k at the from rung not measured")
    at = {k: sup[k] for k in _AT_FROM}
    if at["withinBound"] is not False or not at["share"] > at["maxShare"] or not at["unitsBefore"] > 0:
        raise RunError("rung sacrifice: k at the from rung does not exceed the suppression budget")
    return at


def rung_step(policy, rs: dict, contract: dict, at_from: dict) -> dict:
    """Manifest ``rungStep`` record for an adopted rung sacrifice (aggregates and schema names only)."""
    target = next(t["id"] for t in policy.privacy_targets if t["kind"] == "k_anonymity")
    return {"check": rs["check"], "table": rs["table"], "column": rs["column"], "from": rs["from"], "to": rs["to"],
            "privacyTarget": target, "k": contract["k"], "atFrom": dict(at_from)}


def search_step_at_from(policy, fields: dict, rs: dict, *, source, master, scope_id, recipient) -> dict:
    """k measured at ``rs['from']`` for a search plan: ``fields`` (``{(table, column): (rung, floor)}``, the released
    search plan) with the step's column back at ``from``, rebuilt with the search's own params, through ``protect``
    and ``k_at_from``. One function for ``run`` and ``verify --full``. Fails closed (RunError)."""
    key = (rs["table"], rs["column"])
    at = dict(fields)
    at[key] = (rs["from"], fields[key][1])
    try:
        plan = rebuild_plan(policy, params_from_plan(hand_plan(policy.scenario)), at)
        validate_plan(plan, policy)
    except ValueError as e:  # PlanError is a ValueError; messages are schema names only
        raise RunError(f"rung sacrifice: search plan at the from rung not reproducible ({e})") from None
    *_, sup, _ = protect(plan, policy=policy, source=source, master=master, scope_id=scope_id, recipient=recipient)
    return k_at_from(sup)


def _plan_core(plan) -> list:
    return sorted((e["table"], e["column"], e["rung"], canonical_bytes(e["params"]), e["floor"]) for e in plan)


def require_strict(purpose, steps):
    """A rung sacrifice holds only if its check still passes strictly (status ok, score >= threshold) at `to`."""
    from pets_release.run.purpose import THRESHOLD, PurposeResult

    by = {t["task"]: t for t in purpose.tasks}
    extra = []
    for s in steps:
        t = by.get(s["check"])
        a = None if t is None else t["after"]
        if t is None or t["status"] != "ok" or not isinstance(a, float) or not a >= THRESHOLD:
            extra.append(f"purpose:{s['check']}:rung-sacrifice-not-strict")
    if not extra:
        return purpose
    return PurposeResult(purpose.tasks, tuple(sorted(set(purpose.reasons) | set(extra))))


def run_release(*, kit, scenario: dict, created: str, key_text: str, out, plan_name: str,
                tool_revision: str, recipient: str | None = None, workers: int = 1) -> RunOutcome:
    scenario_id = scenario.get("id")
    if scenario_id not in SCENARIO_SPEC:
        raise RunError("run supports only HEALTH-S1 in this build; the CS-S1 release needs ticket 23 and its "
                       "search is follow-up #96")
    if plan_name not in (None, "hand"):
        raise RunError("unknown --plan: only 'hand' (or no --plan, the search) is supported")
    policy = get_policy(scenario_id)
    if scenario.get("dataset") != policy.dataset:
        raise RunError("scenario dataset differs from the policy dataset")
    out = Path(out).absolute()
    if out.exists() or scoring_dir(out).exists():
        raise RunError("output folder or its scoring folder already exists")

    source = kit.load_dataset(policy.dataset)
    inputs = kit.input_digests(policy.dataset)
    master = MasterKey.from_text(key_text)
    if recipient is None:
        recipient = DEFAULT_RECIPIENT
    else:  # recipient-scoped keys (ticket 28): HKDF key + recipient-bound scope ID; manifest records the ID
        try:
            validate_recipient_id(recipient)
        except RecipientError as e:
            raise RunError(str(e)) from None
    rsid = release_scope_id(scenario=scenario_id, recipient=recipient, inputs=inputs, tool_revision=tool_revision)

    found = None
    if plan_name == "hand":
        plan = hand_plan(scenario_id)
    else:
        found = _search(scenario_id, policy, source, token_keys(master, rsid, recipient), kit, out, workers)
        try:
            check_search_privacy(found.final, policy)
        except RunRefused:
            sc = scoring_dir(out)
            sc.mkdir(parents=True)
            (sc / SEARCH_LOG).write_bytes(search_log_bytes(found.log))
            (sc / "refusal_report.json").write_bytes(canonical_bytes(
                {"status": "refused", "scenario": scenario_id, "reasons": ["search:privacy-recheck-not-pass"],
                 "privacyTargets": found.final["privacy_targets"]}))
            raise
        plan = found.plan
    validate_plan(plan, policy)

    released, finals, suppressed, sup, contract = protect(plan, policy=policy, source=source, master=master,
                                                          scope_id=rsid, recipient=recipient)
    # Enumerated rung sacrifices (#89): measured k at `from` beyond the suppression budget is the only trigger.
    steps = []
    if found is not None:  # a step the search adopted itself: record k at `from` on the search's released plan
        fields = {(e["table"], e["column"]): (e["rung"], e["floor"]) for e in plan}
        try:
            same = _plan_core(rebuild_plan(policy, params_from_plan(hand_plan(scenario_id)), fields)) == \
                _plan_core(plan)
        except ValueError:
            same = False
        if not same:  # verify --full re-measures from the manifest's rungs: they must pin the plan exactly
            raise RunError("search plan is not reproducible from its rungs")
        for rs in policy.rung_sacrifices:
            if fields[(rs["table"], rs["column"])][0] == rs["to"]:
                at_from = search_step_at_from(policy, fields, rs, source=source, master=master, scope_id=rsid,
                                              recipient=recipient)
                steps.append(rung_step(policy, rs, contract, at_from))
    for rs in policy.rung_sacrifices:
        key = (rs["table"], rs["column"])
        entry = next(e for e in plan if (e["table"], e["column"]) == key)
        if _within_bound(out, scenario_id, sup) or entry["rung"] != rs["from"]:
            continue
        at_from = k_at_from(sup)
        plan = [dict(e, rung=rs["to"], params={}, reason=rs["reason"][:500]) if (e["table"], e["column"]) == key
                else e for e in plan]
        validate_plan(plan, policy)
        released, finals, suppressed, sup, contract = protect(plan, policy=policy, source=source, master=master,
                                                              scope_id=rsid, recipient=recipient)
        steps.append(rung_step(policy, rs, contract, at_from))
    if not _within_bound(out, scenario_id, sup):
        _refuse(out, {"status": "refused", "scenario": scenario_id, "reasons": ["suppression:share-above-max"],
                      "suppression": sup})
        raise RunRefused("suppression share above the policy bound")
    if found is not None:
        # The search re-checked every purpose check on its own suppressed tables; release only those rows.
        spec = SCENARIO_SPEC[scenario_id]
        theirs = {t: {source[t].at[i, spec["record_keys"][t]] for i in idx} for t, idx in found.suppressed.items()}
        ours = {t: set(v) for t, v in suppressed.items()}
        if {t: v for t, v in theirs.items() if v} != {t: v for t, v in ours.items() if v}:
            raise RunError("suppression differs from the search's re-checked suppression")

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

    # Full re-check of every purpose check on full data after suppression: a publication prerequisite.
    purpose = evaluate_purpose(policy, source, ordered, root=kit.root)
    purpose = require_strict(purpose, steps)
    if not purpose.ok:
        _refuse(out, {"status": "refused", "scenario": scenario_id, "reasons": list(purpose.reasons),
                      "suppression": sup, "purpose": [dict(t) for t in purpose.tasks]})
        if found is not None:
            (scoring_dir(out) / SEARCH_LOG).write_bytes(search_log_bytes(found.log))
        raise RunRefused("purpose checks failed on the final release: " + ", ".join(purpose.reasons))

    search_info, extra = None, {}
    if found is not None:
        try:
            search_info = {"justifications": justify(plan, found.log, policy),
                           "summary": search_summary(found.log, found.stats), "sacrifices": found.sacrifices}
        except JustificationError as e:
            raise RunError(str(e)) from None
        extra = {SEARCH_LOG: search_log_bytes(found.log)}
    # #146 (D58): per-person k on the scenario's QIs and on every kept catalogued QI, before and after suppression
    k_sets = measure_sets(policy, plan, contract, source=source, master=master, scope_id=rsid, recipient=recipient)
    narrative = build_narrative(policy=policy, plan=plan, scenario_ids=[s["id"] for s in kit.scenarios()],
                                suppression=sup, k=contract["k"], purpose=purpose, search=search_info,
                                rung_steps=steps, k_sets=k_sets)
    cand = Candidate(
        scenario=scenario_id, recipient=recipient, tables=tuple(tables), contract=contract,
        tool_revision=tool_revision, created=created, narrative=narrative,
        # keep/geo rungs carry the gate's `text` form, so text.health runs and needs its lexicon bound
        lexicon_digests={text_checks.LEXICON_NAME: text_checks.lexicon_digest()},
        scoring_files={SUPPRESSION_REPORT: canonical_bytes(sup),
                       PERSON_K_REPORT: canonical_bytes(sup.get("personKAfter", {})), **extra},
    )
    res = write_release(cand, out, master, kit, context=gate_ctx)
    return RunOutcome(res.status, res.out, res.scoring, res.reasons, sup)
