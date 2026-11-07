"""Build a release contract from a scenario policy and a final Plan.

Policy (closed; unknown keys fail). Flags are bools. Names are tokens
``^[A-Za-z0-9_]{1,64}$`` so the result validates in ticket 02's manifest schema
(``derived_from`` cannot contain a dot)::

    {"scenario": "HEALTH-S1",
     "tables": {"ed_visits": {"withheld": False, "columns": {
         "date_of_birth": {"release_name": "age_band", "required": True, "qi": True},
         "visit_id": {"required": True, "token_scope": "release"},
         "sampled_ts": {"qi": True, "derived_from": "join_ed_visits_visit_id"},
     }}}}

``derived_from`` defaults to the source column name. A renamed column
(``age_band``) therefore records ``date_of_birth``. A join-derived QI sets
``derived_from`` to a name token ``join_<table>_<column>`` (no dots).

Plan entries are the pinned shape. One entry per policy column. ``rung`` is a
ladder rung id or ``withheld``. Forms come from ``forms`` or from
``load_forms`` (ticket 07's table, else the fallback). A released column whose
form is missing is rejected. A withheld column or an all-withheld table is
absent. ``privacy_manifest.json`` is not a contract file: ticket 02 equates
``bindings.files`` with ``contract.files``, and file names are ``<table>.csv``.

The digest is SHA-256 hex of the canonical contract. It is not stored in the
contract (it lives in ``bindings.contractDigest``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pets_release.contract.canonical import local_digest, sibling_digest
from pets_release.contract.forms import TOKEN_FORM, load_forms

_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_FILE = re.compile(r"^[A-Za-z0-9_]{1,64}\.csv$")
_RUNG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$")
_PARAM = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_SCOPES = frozenset({"conversation", "recipient", "release"})
_SOURCES = frozenset({"hand", "search"})
_POLICY_KEYS = frozenset({"scenario", "tables"})
_TABLE_KEYS = frozenset({"columns", "withheld"})
_COLUMN_KEYS = frozenset({"derived_from", "qi", "release_name", "required", "token_scope"})
_PLAN_KEYS = frozenset({"column", "floor", "params", "reason", "rung", "source", "table"})
_CONTRACT_KEYS = frozenset({"files", "qi", "tokens"})
_FILE_KEYS = frozenset({"columns", "required"})
_COL_KEYS = frozenset({"form", "params"})
_QI_KEYS = frozenset({"column", "derived_from", "table"})
_TOKEN_KEYS = frozenset({"column", "scope", "table"})
_RESERVED_PARAMS = frozenset({"derived_from", "rung"})
_FORM_MAX = 300
_PARAM_STR_MAX = 200


class ContractError(ValueError):
    """Generation or digest rejected. Message is schema names and rule ids only."""


def generate(
    policy: Mapping[str, Any],
    plan: Sequence[Mapping[str, Any]],
    *,
    forms: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the contract. Raises ContractError; does not return a partial."""
    parsed_policy = _parse_policy(policy)
    entries = _parse_plan(plan)
    form_table = _form_table(forms)
    _cover(parsed_policy, entries)

    files: dict[str, dict[str, Any]] = {}
    qi: list[dict[str, str]] = []
    tokens: list[dict[str, str]] = []

    for table in sorted(parsed_policy):
        spec = parsed_policy[table]
        released: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for column in sorted(spec["columns"]):
            meta = spec["columns"][column]
            entry = entries[(table, column)]
            if entry["rung"] == "withheld":
                if meta["required"]:
                    raise ContractError(f"{table}.{column}: required column withheld")
                continue
            if spec["withheld"]:
                raise ContractError(f"{table}.{column}: released in withheld table")
            release_name = meta["release_name"] or column
            if not _NAME.fullmatch(release_name):
                raise ContractError(f"{table}.{column}: release name not a name token")
            if release_name in released:
                raise ContractError(f"{table}.{release_name}: duplicate release name")
            form = _require_form(form_table, table, column, entry["rung"])
            scope = meta["token_scope"]
            if form == TOKEN_FORM and not scope:
                raise ContractError(f"{table}.{column}: token scope missing")
            if scope and scope not in _SCOPES:
                raise ContractError(f"{table}.{column}: token scope invalid")
            if scope and form != TOKEN_FORM:
                raise ContractError(f"{table}.{column}: token scope on non-token form")
            deriv = meta["derived_from"] or column
            params = dict(entry["params"])
            params["rung"] = entry["rung"]
            if release_name != column or deriv != column:
                params["derived_from"] = deriv
            released[release_name] = {"form": form, "params": _sorted_params(params)}
            if meta["required"]:
                required.append(release_name)
            if meta["qi"]:
                qi.append({"table": table, "column": release_name, "derived_from": deriv})
            if scope:
                tokens.append({"table": table, "column": release_name, "scope": scope})
        if released:
            files[f"{table}.csv"] = {
                "columns": dict(sorted(released.items())),
                "required": sorted(required),
            }

    if not files:
        raise ContractError("no released files")
    contract = {
        "files": dict(sorted(files.items())),
        "qi": sorted(qi, key=lambda row: (row["table"], row["column"])),
        "tokens": sorted(tokens, key=lambda row: (row["table"], row["column"])),
    }
    _validate_contract(contract)
    return contract


def digest(contract: Mapping[str, Any]) -> str:
    """SHA-256 hex of the canonical contract. Rejects a closed-record violation."""
    _validate_contract(contract)
    sibling = sibling_digest()
    if sibling is not None:
        return sibling(contract)
    return local_digest(contract)


def _form_table(forms: Mapping[str, str] | None) -> Mapping[str, Any]:
    if forms is None:
        return load_forms()
    if not isinstance(forms, Mapping):
        raise ContractError("forms: not an object")
    return forms


def _require_form(forms: Mapping[str, Any], table: str, column: str, rung: str) -> str:
    form = forms.get(rung)
    if not isinstance(form, str) or not form.strip():
        raise ContractError(f"{table}.{column}: form missing for rung {rung}")
    if len(form) > _FORM_MAX:
        raise ContractError(f"{table}.{column}: form too long")
    try:
        re.compile(form)
    except re.error:
        raise ContractError(f"{table}.{column}: form not a regex") from None
    return form


def _parse_policy(policy: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(policy, Mapping):
        raise ContractError("policy: not an object")
    _exact(policy, _POLICY_KEYS, "policy", allow_missing=frozenset())
    scenario = policy["scenario"]
    if not isinstance(scenario, str) or not _RUNG.fullmatch(scenario):
        raise ContractError("policy.scenario: invalid")
    tables = policy["tables"]
    if not isinstance(tables, Mapping) or not tables:
        raise ContractError("policy.tables: invalid")
    parsed: dict[str, dict[str, Any]] = {}
    for table, spec in tables.items():
        if not isinstance(table, str) or not _NAME.fullmatch(table):
            raise ContractError("policy.tables: table name")
        if not isinstance(spec, Mapping):
            raise ContractError(f"{table}: not an object")
        _exact(spec, _TABLE_KEYS, table, allow_missing=frozenset({"withheld"}))
        withheld = spec.get("withheld", False)
        if not isinstance(withheld, bool):
            raise ContractError(f"{table}.withheld: not a bool")
        columns = spec.get("columns")
        if not isinstance(columns, Mapping) or not columns:
            raise ContractError(f"{table}: columns missing")
        parsed_cols: dict[str, dict[str, Any]] = {}
        for column, meta in columns.items():
            if not isinstance(column, str) or not _NAME.fullmatch(column):
                raise ContractError(f"{table}: column name")
            if not isinstance(meta, Mapping):
                raise ContractError(f"{table}.{column}: not an object")
            _exact(meta, _COLUMN_KEYS, f"{table}.{column}", allow_missing=_COLUMN_KEYS)
            parsed_cols[column] = {
                "release_name": _optional_name(meta, "release_name", f"{table}.{column}"),
                "required": _optional_bool(meta, "required", f"{table}.{column}"),
                "qi": _optional_bool(meta, "qi", f"{table}.{column}"),
                "token_scope": _optional_scope(meta, f"{table}.{column}"),
                "derived_from": _optional_name(meta, "derived_from", f"{table}.{column}"),
            }
        parsed[table] = {"withheld": withheld, "columns": parsed_cols}
    return parsed


def _parse_plan(plan: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    if isinstance(plan, (str, bytes)) or not isinstance(plan, Sequence):
        raise ContractError("plan: not a list")
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(plan):
        where = f"plan[{index}]"
        if not isinstance(raw, Mapping):
            raise ContractError(f"{where}: not an object")
        _exact(raw, _PLAN_KEYS, where, allow_missing=frozenset())
        table, column = raw["table"], raw["column"]
        if not isinstance(table, str) or not _NAME.fullmatch(table):
            raise ContractError(f"{where}: table name")
        if not isinstance(column, str) or not _NAME.fullmatch(column):
            raise ContractError(f"{where}: column name")
        rung = raw["rung"]
        if not isinstance(rung, str) or not _RUNG.fullmatch(rung):
            raise ContractError(f"{table}.{column}: rung")
        source = raw["source"]
        if source not in _SOURCES:
            raise ContractError(f"{table}.{column}: source")
        for field in ("floor", "reason"):
            value = raw[field]
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{table}.{column}: {field}")
        if not _RUNG.fullmatch(raw["floor"]):
            raise ContractError(f"{table}.{column}: floor")
        params = _parse_params(raw["params"], f"{table}.{column}")
        key = (table, column)
        if key in entries:
            raise ContractError(f"{table}.{column}: duplicate plan entry")
        entries[key] = {"rung": rung, "params": params}
    if not entries:
        raise ContractError("plan: empty")
    return entries


def _parse_params(params: Any, where: str) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise ContractError(f"{where}: params")
    out: dict[str, Any] = {}
    for key, value in params.items():
        if not isinstance(key, str) or not _PARAM.fullmatch(key):
            raise ContractError(f"{where}: param name")
        if key in _RESERVED_PARAMS:
            raise ContractError(f"{where}: reserved param {key}")
        out[key] = _param_value(value, where)
    return out


def _param_value(value: Any, where: str) -> Any:
    if isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        if len(value) > _PARAM_STR_MAX:
            raise ContractError(f"{where}: param too long")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{where}: param not finite")
        if value.is_integer() and abs(value) < 2**53:
            return int(value)
        raise ContractError(f"{where}: param float")
    raise ContractError(f"{where}: param type")


def _cover(policy: dict[str, dict[str, Any]], entries: dict[tuple[str, str], dict[str, Any]]) -> None:
    expected = {(table, column) for table, spec in policy.items() for column in spec["columns"]}
    missing = sorted(expected - set(entries))
    extra = sorted(set(entries) - expected)
    if missing:
        table, column = missing[0]
        raise ContractError(f"{table}.{column}: plan entry missing")
    if extra:
        table, column = extra[0]
        raise ContractError(f"{table}.{column}: not in policy")


def _validate_contract(contract: Mapping[str, Any]) -> None:
    if not isinstance(contract, Mapping):
        raise ContractError("contract: not an object")
    _exact(contract, _CONTRACT_KEYS, "contract", allow_missing=frozenset())
    files = contract["files"]
    if not isinstance(files, Mapping) or not files:
        raise ContractError("contract: no released files")
    for name, spec in files.items():
        if not isinstance(name, str) or not _FILE.fullmatch(name):
            raise ContractError("contract: file name")
        if not isinstance(spec, Mapping):
            raise ContractError(f"{name}: not an object")
        _exact(spec, _FILE_KEYS, name, allow_missing=frozenset())
        required = spec["required"]
        columns = spec["columns"]
        if not isinstance(columns, Mapping) or not columns:
            raise ContractError(f"{name}: columns")
        if not isinstance(required, list) or required != sorted(required) or len(required) != len(set(required)):
            raise ContractError(f"{name}: required unsorted")
        if not set(required) <= set(columns):
            raise ContractError(f"{name}: required not in columns")
        for column, body in columns.items():
            if not isinstance(column, str) or not _NAME.fullmatch(column):
                raise ContractError(f"{name}: column name")
            if not isinstance(body, Mapping):
                raise ContractError(f"{name}.{column}: not an object")
            _exact(body, _COL_KEYS, f"{name}.{column}", allow_missing=frozenset())
            form = body["form"]
            if not isinstance(form, str) or not form.strip() or len(form) > _FORM_MAX:
                raise ContractError(f"{name}.{column}: form")
            params = body["params"]
            if not isinstance(params, Mapping):
                raise ContractError(f"{name}.{column}: params")
            for key, value in params.items():
                if not isinstance(key, str) or not _PARAM.fullmatch(key):
                    raise ContractError(f"{name}.{column}: param name")
                if isinstance(value, str) and len(value) > _PARAM_STR_MAX:
                    raise ContractError(f"{name}.{column}: param too long")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ContractError(f"{name}.{column}: param not finite")
                if not isinstance(value, (str, int, float, bool)):
                    raise ContractError(f"{name}.{column}: param type")
    _validate_named_list(contract["qi"], _QI_KEYS, "qi", ("table", "column"))
    _validate_named_list(contract["tokens"], _TOKEN_KEYS, "tokens", ("table", "column"))
    for row in contract["tokens"]:
        if row["scope"] not in _SCOPES:
            raise ContractError("tokens: scope")
    for row in contract["qi"]:
        if not _NAME.fullmatch(row["derived_from"]):
            raise ContractError("qi: derived_from")


def _validate_named_list(rows: Any, keys: frozenset[str], label: str, sort_fields: tuple[str, ...]) -> None:
    if not isinstance(rows, list):
        raise ContractError(f"{label}: not a list")
    seen: list[tuple[str, ...]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ContractError(f"{label}: not an object")
        _exact(row, keys, label, allow_missing=frozenset())
        for field in keys:
            if not isinstance(row[field], str) or not row[field]:
                raise ContractError(f"{label}: {field}")
        if not _NAME.fullmatch(row["table"]) or not _NAME.fullmatch(row["column"]):
            raise ContractError(f"{label}: name")
        seen.append(tuple(row[field] for field in sort_fields))
    if seen != sorted(seen) or len(seen) != len(set(seen)):
        raise ContractError(f"{label}: unsorted")


def _exact(obj: Mapping[str, Any], allowed: frozenset[str], where: str, *, allow_missing: frozenset[str]) -> None:
    unknown = set(obj) - allowed
    if unknown:
        key = min(unknown)
        raise ContractError(f"{where}: unknown key {key}")
    missing = (allowed - allow_missing) - set(obj)
    if missing:
        key = min(missing)
        raise ContractError(f"{where}: missing key {key}")


def _optional_bool(meta: Mapping[str, Any], key: str, where: str) -> bool:
    if key not in meta:
        return False
    value = meta[key]
    if not isinstance(value, bool):
        raise ContractError(f"{where}.{key}: not a bool")
    return value


def _optional_name(meta: Mapping[str, Any], key: str, where: str) -> str | None:
    if key not in meta:
        return None
    value = meta[key]
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ContractError(f"{where}.{key}: not a name token")
    return value


def _optional_scope(meta: Mapping[str, Any], where: str) -> str | None:
    if "token_scope" not in meta:
        return None
    value = meta["token_scope"]
    if not isinstance(value, str) or value not in _SCOPES:
        raise ContractError(f"{where}: token scope invalid")
    return value


def _sorted_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: params[key] for key in sorted(params)}
