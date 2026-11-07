"""``pets-release run`` (loaded by the 01 dispatcher as ``pets_release.run.cli:main(argv)``).

Exit 0 released, 1 refused, 2 usage error or unknown state. Prints aggregates only: gate check counts by status,
refusal reason codes, suppression share and the per-person k summary.
"""
from __future__ import annotations

import sys

from pets_release.cli import UsageError, resolve_run_context
from pets_release.manifest import loads_strict
from pets_release.recipient import RecipientError, validate_recipient_id
from pets_release.run.pipeline import RunError, RunRefused, run_release


def _print_gate(scoring) -> None:
    for name in ("gate_report.json", "refusal_report.json"):
        p = scoring / name
        if not p.is_file():
            continue
        rep = loads_strict(p.read_bytes())
        gate = rep.get("gate", rep)
        recs = gate.get("records", []) if isinstance(gate, dict) else []
        by: dict[str, int] = {}
        for r in recs:
            by[r["status"]] = by.get(r["status"], 0) + 1
        hits = sum(r.get("hits", 0) for r in recs)
        print(f"gate: {len(recs)} checks, " + ", ".join(f"{k}={v}" for k, v in sorted(by.items()))
              + f", hits={hits}")
        for r in recs:
            if r["status"] not in ("pass", "not_applicable") or r.get("hits"):
                print(f"  check {r['check']}: {r['status']} (hits={r.get('hits')})")


def main(argv: list[str]) -> int:
    try:
        ctx = resolve_run_context(argv)
    except UsageError as e:
        print(f"pets-release run: {e}", file=sys.stderr)
        return 2
    a = ctx.args
    if a.sample is not None:
        print("pets-release run: --sample is not supported in this build", file=sys.stderr)
        return 2
    if a.recipient is not None:
        try:
            validate_recipient_id(a.recipient)
        except RecipientError as e:
            print(f"pets-release run: {e}", file=sys.stderr)
            return 2
    from pets_release.verify import current_tool_revision

    rev = current_tool_revision()
    if rev is None:
        print("pets-release run: tool revision unavailable (git HEAD)", file=sys.stderr)
        return 2
    try:
        res = run_release(kit=ctx.kit, scenario=ctx.scenario, created=ctx.created, key_text=ctx.key,
                          out=a.out, plan_name=a.plan, tool_revision=rev,
                          recipient=a.recipient)
    except RunError as e:
        print(f"pets-release run: {e}", file=sys.stderr)
        return 2
    except RunRefused as e:
        print(f"REFUSED: {e}")
        return 1
    sup = res.suppression
    if sup.get("method") == "local_suppression":
        print(f"suppression: {sup['unitsSuppressed']}/{sup['unitsBefore']} persons (share {sup['share']}, "
              f"max {sup['maxShare']}), rounds={sup['rounds']}, rows={sup['rowsSuppressed']}")
        after = sup["personKAfter"]
        print(f"person-k: persons={after['persons']} minK={after['minK']} medianK={after['medianK']} "
              f"belowK={after['belowK']} distribution={after['distribution']}")
    _print_gate(res.scoring)
    if res.status == "released":
        print(f"RELEASED: {res.out.name} (scoring: {res.scoring.name})")
        return 0
    print(f"REFUSED: {len(res.reasons)} reason(s)")
    for r in res.reasons:
        print(f"  {r}")
    return 1
