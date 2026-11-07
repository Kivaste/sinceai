"""Print the contracts for both hand plans: schema names and forms only, no row values.

    python -m pets_release.contract [OUT_DIR]

Writes ``contracts.txt`` and one ``<scenario>.contract.json`` to OUT_DIR when given.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pets_release.contract.generate import ContractError, digest, generate
from pets_release.manifest import canonical_bytes
from pets_release.policy import get_policy, hand_plan

SCENARIOS = ("HEALTH-S1", "CS-S1")


def render(scenario: str) -> tuple[str, dict]:
    policy = get_policy(scenario)
    contract = generate(policy, hand_plan(scenario))
    qi = {(r["table"], r["column"]): r["derived_from"] for r in contract["qi"]}
    tokens = {(r["table"], r["column"]): r["scope"] for r in contract["tokens"]}
    lines = [f"scenario {scenario} digest {digest(contract)}"]
    present_tables = set()
    for filename, spec in contract["files"].items():
        table = filename[: -len(".csv")]
        present_tables.add(table)
        lines.append(f"file {filename}")
        for column, body in spec["columns"].items():
            params = body["params"]
            lines.append(
                f"  column {column} form={body['form']} rung={params['rung']}"
                f" required={column in spec['required']} qi={qi.get((table, column), '-')}"
                f" token={tokens.get((table, column), '-')} derived_from={params.get('derived_from', '-')}"
            )
    for table in sorted({t for t, _ in policy.floors} - present_tables):
        lines.append(f"absent_table {table}")
    return "\n".join(lines) + "\n", contract


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else None
    chunks = []
    try:
        for scenario in SCENARIOS:
            text, contract = render(scenario)
            chunks.append(text)
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{scenario}.contract.json").write_bytes(canonical_bytes(contract))
    except ContractError as exc:
        sys.stderr.write(f"contract rejected: {exc}\n")
        return 1
    text = "".join(chunks)
    sys.stdout.write(text)
    if out_dir is not None:
        (out_dir / "contracts.txt").write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
