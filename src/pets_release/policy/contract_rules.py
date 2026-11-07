"""The pinned scenario policy constrains a release contract (#62). Schema names only; no row values.

A contract cannot set its own privacy target: the k target comes from the policy's ``k_anonymity`` privacy
target, and every policy QI the contract releases must be listed in ``contract.qi``. The writer refuses on any
problem before the gate, and manifest validation applies the same rule (every verify tier, the dashboard).
"""
from __future__ import annotations

from collections.abc import Mapping


def _valid_k(k) -> bool:
    return isinstance(k, int) and not isinstance(k, bool) and k >= 2


def k_target(policy) -> int | None:
    """The policy's k-anonymity target, or None when it has none. Raises ValueError on a malformed target."""
    targets = [t for t in policy.privacy_targets if t.get("kind") == "k_anonymity"]
    if not targets:
        return None
    if len(targets) > 1 or not _valid_k(targets[0].get("k")):
        raise ValueError("policy k_anonymity target is malformed")
    return targets[0]["k"]


def released_policy_qis(policy, contract: Mapping) -> list[tuple[str, str]]:
    """(table, released column) of every policy QI the contract releases (derived name, or source name)."""
    files = contract.get("files") if isinstance(contract, Mapping) else None
    if not isinstance(files, Mapping):
        return []
    out = set()
    for q in policy.qi:
        spec = files.get(f"{q['table']}.csv")
        cols = spec.get("columns") if isinstance(spec, Mapping) else None
        if not isinstance(cols, Mapping):
            continue
        for name in {q["derived"], q["column"]}:
            if name in cols:
                out.add((q["table"], name))
    return sorted(out)


def contract_policy_problems(scenario: str, contract) -> list[str]:
    """Content-free problem codes (``<field>: <rule>``); ``[]`` means the contract honours the policy."""
    from pets_release.policy import get_policy

    try:
        policy = get_policy(scenario)
    except KeyError:
        return ["scenario: no-policy"]
    if not isinstance(contract, Mapping):
        return ["contract: unreadable"]
    out = []
    try:
        want = k_target(policy)
    except ValueError:
        return ["policy: malformed-k-target"]
    if want is None:
        if "k" in contract:
            out.append("contract.k: not-in-policy")
    elif "k" not in contract:
        out.append("contract.k: missing")
    elif not _valid_k(contract["k"]) or contract["k"] != want:
        out.append("contract.k: policy-mismatch")
    qi = contract.get("qi")
    listed = {(q.get("table"), q.get("column")) for q in qi if isinstance(q, Mapping)} if isinstance(qi, list) else set()
    for table, column in released_policy_qis(policy, contract):
        if (table, column) not in listed:
            out.append(f"contract.qi: {table}.{column}: missing-policy-qi")
    return sorted(out)
