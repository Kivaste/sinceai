"""Spec-derived HEALTH-S1 and CS-S1 hand plans for contract evidence.

Not the scenario-policy package (ticket 09). ``resolve_plans`` uses
``pets_release.policy.hand_plans`` or ``HAND_PLANS`` when that module is
importable, and these fixtures otherwise. Rung ids are the fallback table's
ids until ticket 07 lands. "Search decides" choices are noted in the report.

Run: ``python -m pets_release.contract.hand_plans``
Prints schema names and forms only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pets_release.contract.generate import ContractError, digest, generate

# (table, column, rung, flags). flags: release_name, required, qi, token_scope,
# derived_from, params, table_withheld.
_Row = tuple[str, str, str, dict[str, Any]]

_HEALTH: tuple[_Row, ...] = (
    ("ed_visits", "visit_id", "identifier.pseudonym", {"required": True, "token_scope": "release"}),
    ("ed_visits", "patient_hetu", "withheld", {}),
    ("ed_visits", "patient_name", "withheld", {}),
    ("ed_visits", "date_of_birth", "age.band10", {
        "release_name": "age_band", "required": True, "qi": True, "params": {"width": 10, "top": 90},
    }),
    ("ed_visits", "sex", "category.sex", {"qi": True}),
    ("ed_visits", "phone", "withheld", {}),
    ("ed_visits", "home_address", "withheld", {}),
    ("ed_visits", "postcode", "withheld", {}),
    ("ed_visits", "municipality", "geo.full", {"required": True, "qi": True}),
    ("ed_visits", "arrival_ts", "timestamp.month_hour", {"required": True, "qi": True}),
    ("ed_visits", "arrival_mode", "category.arrival_mode", {"qi": True}),
    ("ed_visits", "ambulance_unit", "identifier.pseudonym", {"token_scope": "release"}),
    ("ed_visits", "triage", "category.triage", {"required": True}),
    ("ed_visits", "chief_complaint", "withheld", {}),
    ("ed_visits", "icd10_primary", "icd10.3char", {"required": True}),
    ("ed_visits", "icd10_secondary", "icd10.3char", {}),
    ("ed_visits", "systolic_bp", "numeric.exact", {}),
    ("ed_visits", "diastolic_bp", "numeric.exact", {}),
    ("ed_visits", "heart_rate", "numeric.exact", {}),
    ("ed_visits", "resp_rate", "numeric.exact", {}),
    ("ed_visits", "temp_c", "numeric.exact", {"required": True}),
    ("ed_visits", "spo2", "numeric.exact", {}),
    ("ed_visits", "pain_nrs", "numeric.exact", {}),
    ("ed_visits", "attending_physician_id", "identifier.pseudonym", {"token_scope": "release"}),
    ("ed_visits", "attending_physician_name", "withheld", {}),
    ("ed_visits", "discharge_ts", "withheld", {}),
    ("ed_visits", "los_minutes", "numeric.exact", {"required": True}),
    ("ed_visits", "disposition", "category.disposition", {}),
    ("ed_visits", "readmit_30d", "flag.exact", {"required": True}),
    ("lab_results", "lab_id", "identifier.pseudonym", {"token_scope": "release"}),
    ("lab_results", "visit_id", "identifier.pseudonym", {"required": True, "token_scope": "release"}),
    ("lab_results", "test_code", "category.exact", {"required": True}),
    ("lab_results", "test_name", "category.exact", {}),
    ("lab_results", "value", "numeric.exact", {"required": True}),
    ("lab_results", "unit", "category.exact", {}),
    ("lab_results", "ref_range", "category.exact", {}),
    ("lab_results", "abnormal_flag", "category.abnormal", {}),
    ("lab_results", "sampled_ts", "withheld", {"qi": True, "derived_from": "join_ed_visits_visit_id"}),
    ("clinical_notes", "note_id", "withheld", {"table_withheld": True}),
    ("clinical_notes", "visit_id", "withheld", {"table_withheld": True}),
    ("clinical_notes", "note_type", "withheld", {"table_withheld": True}),
    ("clinical_notes", "author_staff_id", "withheld", {"table_withheld": True}),
    ("clinical_notes", "author_name", "withheld", {"table_withheld": True}),
    ("clinical_notes", "written_ts", "withheld", {"table_withheld": True}),
    ("clinical_notes", "language", "withheld", {"table_withheld": True}),
    ("clinical_notes", "note_text", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "stat_id", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "week", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "municipality", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "age_band", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "sex", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "diagnosis_group", "withheld", {"table_withheld": True}),
    ("published_weekly_stats", "visits", "withheld", {"table_withheld": True}),
)

_CS: tuple[_Row, ...] = (
    ("conversations", "conversation_id", "identifier.pseudonym", {"required": True, "token_scope": "release"}),
    ("conversations", "customer_id", "withheld", {}),
    ("conversations", "agent_id", "identifier.pseudonym", {"token_scope": "release"}),
    ("conversations", "agent_name", "withheld", {}),
    ("conversations", "channel", "category.channel", {}),
    ("conversations", "language", "category.language", {"qi": True}),
    ("conversations", "started_ts", "timestamp.hour", {"qi": True}),
    ("conversations", "intent", "category.exact", {"required": True}),
    ("conversations", "sentiment", "category.exact", {}),
    ("conversations", "csat", "numeric.csat", {}),
    ("conversations", "resolved", "category.exact", {}),
    ("conversations", "handle_time_s", "numeric.exact", {"required": True}),
    ("conversations", "n_turns", "numeric.exact", {}),
    ("conversations", "split", "category.split", {"required": True}),
    ("conversations", "agent_note", "withheld", {}),
    ("customers", "customer_id", "withheld", {"table_withheld": True}),
    ("customers", "customer_number", "withheld", {"table_withheld": True}),
    ("customers", "full_name", "withheld", {"table_withheld": True}),
    ("customers", "hetu", "withheld", {"table_withheld": True}),
    ("customers", "street_address", "withheld", {"table_withheld": True}),
    ("customers", "postcode", "withheld", {"table_withheld": True}),
    ("customers", "city", "withheld", {"table_withheld": True}),
    ("customers", "email", "withheld", {"table_withheld": True}),
    ("customers", "phone", "withheld", {"table_withheld": True}),
    ("customers", "preferred_language", "withheld", {"table_withheld": True}),
    ("customers", "customer_since", "withheld", {"table_withheld": True}),
    ("customers", "products", "withheld", {"table_withheld": True}),
    ("customers", "contract_number", "withheld", {"table_withheld": True}),
    ("customers", "payment_method", "withheld", {"table_withheld": True}),
    ("customers", "iban", "withheld", {"table_withheld": True}),
    ("customers", "marketing_consent", "withheld", {"table_withheld": True}),
    ("customers", "payment_default_flag", "withheld", {"table_withheld": True}),
    ("customers", "accessibility_needs", "withheld", {"table_withheld": True}),
    ("turns", "turn_id", "as_is", {"required": True}),
    ("turns", "conversation_id", "identifier.pseudonym", {"required": True, "token_scope": "release"}),
    ("turns", "seq", "numeric.exact", {}),
    ("turns", "speaker", "category.speaker", {}),
    ("turns", "ts", "timestamp.hour", {"qi": True}),
    ("turns", "text", "text.redacted", {"required": True}),
)

_FLAG_KEYS = ("derived_from", "qi", "release_name", "required", "token_scope")


def _pack(scenario: str, rows: tuple[_Row, ...]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tables: dict[str, dict[str, Any]] = {}
    plan: list[dict[str, Any]] = []
    for table, column, rung, flags in rows:
        spec = tables.setdefault(table, {"columns": {}})
        if flags.get("table_withheld"):
            spec["withheld"] = True
        column_spec = {key: flags[key] for key in _FLAG_KEYS if key in flags}
        spec["columns"][column] = column_spec
        plan.append({
            "table": table,
            "column": column,
            "rung": rung,
            "params": dict(flags.get("params", {})),
            "floor": rung,
            "reason": "hand",
            "source": "hand",
        })
    return {"scenario": scenario, "tables": tables}, plan


def health_plan() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _pack("HEALTH-S1", _HEALTH)


def cs_plan() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _pack("CS-S1", _CS)


def local_plans() -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    health, cs = health_plan(), cs_plan()
    return [("HEALTH-S1", health[0], health[1]), ("CS-S1", cs[0], cs[1])]


def resolve_plans() -> tuple[list[tuple[str, dict[str, Any], list[dict[str, Any]]]], str]:
    """Policy-module hand plans when ticket 09 has landed, else the local fixtures."""
    try:
        from pets_release import policy
    except ImportError:
        return local_plans(), "local"
    if hasattr(policy, "hand_plans"):
        raw = policy.hand_plans()
    elif hasattr(policy, "HAND_PLANS"):
        raw = policy.HAND_PLANS
    else:
        raise ContractError("pets_release.policy: hand plans missing")
    packed = _coerce_sibling(raw)
    return packed, "policy"


def _coerce_sibling(raw: Any) -> list[tuple[str, dict[str, Any], list[dict[str, Any]]]]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ContractError("pets_release.policy: hand plans shape")
    out = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ContractError("pets_release.policy: hand plans shape")
        scenario, policy, plan = item
        if not isinstance(scenario, str) or not isinstance(policy, dict) or not isinstance(plan, list):
            raise ContractError("pets_release.policy: hand plans shape")
        out.append((scenario, policy, plan))
    return out


def render(plans: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] | None = None) -> str:
    """Schema names and forms only. No row values."""
    chosen = local_plans() if plans is None else plans
    lines: list[str] = []
    for scenario, policy, plan in chosen:
        contract = generate(policy, plan)
        lines.append(
            f"scenario {scenario} digest {digest(contract)} "
            f"files {len(contract['files'])} columns {_column_count(contract)} "
            f"qi {len(contract['qi'])} tokens {len(contract['tokens'])}"
        )
        qi = {(row["table"], row["column"]): row["derived_from"] for row in contract["qi"]}
        tokens = {(row["table"], row["column"]): row["scope"] for row in contract["tokens"]}
        released_tables = set()
        for filename, spec in contract["files"].items():
            table = filename[: -len(".csv")]
            released_tables.add(table)
            lines.append(f"file {filename}")
            required = set(spec["required"])
            for column, body in spec["columns"].items():
                lines.append(
                    "column {column} required={req} form={form} rung={rung} qi={qi} token={token}".format(
                        column=column,
                        req="true" if column in required else "false",
                        form=body["form"],
                        rung=body["params"].get("rung", "-"),
                        qi=qi.get((table, column), "-"),
                        token=tokens.get((table, column), "-"),
                    )
                )
        for table, spec in sorted(policy["tables"].items()):
            if table not in released_tables:
                lines.append(f"absent_table {table}")
            for column, meta in spec["columns"].items():
                release_name = meta.get("release_name", column)
                file_spec = contract["files"].get(f"{table}.csv")
                present = file_spec is not None and release_name in file_spec["columns"]
                if present and release_name != column:
                    lines.append(f"renamed {table}.{column} {release_name}")
                elif not present:
                    lines.append(f"absent_column {table}.{column}")
    lines.append("")
    return "\n".join(lines)


def _column_count(contract: dict[str, Any]) -> int:
    return sum(len(spec["columns"]) for spec in contract["files"].values())


def main() -> None:
    plans, source = resolve_plans()
    text = f"source {source}\n" + render(plans)
    sys.stdout.write(text)
    out_dir = Path(r"C:\Users\kivas\AI\sinceai-out\10")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "contracts.txt").write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
