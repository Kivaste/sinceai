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
from pets_release.minimiser import LOG_KEYS, MinimiserRefused, search
from pets_release.minimiser.kit import search_options
from pets_release.policy import get_policy, hand_plan, validate_plan
from pets_release.pseudonym import MasterKey
from pets_release.recipient import RecipientError, validate_recipient_id
from pets_release.run.context import DEFAULT_RECIPIENT, SCENARIO_SPEC, producer_context, token_keys
from pets_release.run.justify import JustificationError, justify, search_summary
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
    empty list. Anything else not ``pass`` refuses (RunRefused); a malformed or self-contradicting result is an
    unknown state (RunError)."""
    if not isinstance(final, dict) or "privacy_status" not in final or "privacy_targets" not in final:
        raise RunError("search result has no privacy re-check")
    status, targets = final["privacy_status"], final["privacy_targets"]
    if not isinstance(targets, list) or not all(isinstance(t, dict) for t in targets):
        raise RunError("search privacy targets malformed")
    declared = sorted((str(t.get("id")), str(t.get("kind"))) for t in policy.privacy_targets)
    if status == "not_applicable":
        if declared or targets:
            raise RunRefused("search privacy re-check not applicable although the policy declares targets")
        return
    if status != "pass":
        raise RunRefused(f"search privacy re-check: {status}")
    got = sorted((str(t.get("id")), str(t.get("kind"))) for t in targets)
    if not declared or got != declared or any(t.get("status") != "pass" for t in targets):
        raise RunError("search privacy re-check contradicts the policy targets")


def _search(scenario_id, policy, source, keys, kit, out: Path):
    """The bounded search (ticket 24) on the full source; a refusal writes its report and log, then raises."""
    try:
        return search(policy, source, keys, **search_options(scenario_id, kit.root, hand_plan(scenario_id)))
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


def run_release(*, kit, scenario: dict, created: str, key_text: str, out, plan_name: str,
                tool_revision: str, recipient: str | None = None) -> RunOutcome:
    scenario_id = scenario.get("id")
    if scenario_id not in SCENARIO_SPEC:
        raise RunError("run supports only HEALTH-S1 in this build")
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
    keys = token_keys(master, rsid, recipient)

    found = None
    if plan_name == "hand":
        plan = hand_plan(scenario_id)
    else:
        found = _search(scenario_id, policy, source, keys, kit, out)
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

    released = apply_plan(plan, source, keys)
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
        _refuse(out, {"status": "refused", "scenario": scenario_id, "reasons": ["suppression:share-above-max"],
                      "suppression": sup})
        raise RunRefused("suppression share above the policy bound")
    if found is not None:
        # The search re-checked every purpose check on its own suppressed tables; release only those rows.
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
    narrative = build_narrative(policy=policy, plan=plan, scenario_ids=[s["id"] for s in kit.scenarios()],
                                suppression=sup, k=contract["k"], purpose=purpose, search=search_info)
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
