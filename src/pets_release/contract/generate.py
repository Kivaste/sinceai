"""Build the release contract from a ``ScenarioPolicy`` (ticket 09) and the final Plan.

Everything comes from the canonical sources, with no fallbacks:

* rung -> form: ``pets_release.ladders.contract_form`` (ticket 07); the form must be one of the
  gate's validator IDs or an anchored regex ``^...$`` (ticket 04), else generation is rejected;
* release column name: ``pets_release.ladders.output_column`` (age rungs yield ``age_band``);
* QI rows: ``policy.qi`` (ticket 09), kept only when the column is released. A policy QI row may
  carry ``join_via: [table, column]``; its derivation is then the name ``join_<table>_<column>``;
  otherwise the derivation is the source column;
* token scope: ``release`` for every ``id.pseudonym`` entry (07 binds that scope inside ``apply``);
  an explicit other ``params["scope"]`` is rejected;
* digest: ``pets_release.manifest.canonical_digest`` (ticket 02).

Contract shape (what 02's schema stores and 04's contract checks read)::

    {"files": {"<table>.csv": {"columns": {name: {"form", "params"}}, "required": [...]}},
     "qi": [{"table", "column", "derived_from"}], "tokens": [{"table", "column", "scope"}]}

Every released column is required (the ladders' ``apply`` emits all of them) and nullable
(source columns may contain empty cells). ``params`` also carries ``rung`` and, for a derived or
renamed column, ``derived_from`` (the source column). Withheld columns and tables are absent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pets_release.ladders import (
    VALIDATOR_FORMS,
    LadderError,
    contract_form,
    output_column,
)
from pets_release.manifest import canonical_digest

_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_FILE = re.compile(r"^[A-Za-z0-9_]{1,64}\.csv$")
_SCOPES = frozenset({"conversation", "recipient", "release"})
_PLAN_KEYS = frozenset({"column", "floor", "params", "reason", "rung", "source", "table"})
_CONTRACT_KEYS = frozenset({"files", "qi", "tokens"})
_FILE_KEYS = frozenset({"columns", "required"})
_COL_KEYS = frozenset({"form", "params"})
_QI_KEYS = frozenset({"column", "derived_from", "table"})
_TOKEN_KEYS = frozenset({"column", "scope", "table"})
_FORM_MAX = 300
_WITHHELD = "withheld"
_PSEUDONYM_SCOPE = "release"  # ticket 07 binds id.pseudonym to the release scope


class ContractError(ValueError):
    """Generation or digest rejected. Messages carry schema names and rule ids only."""


def generate(policy: Any, plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the contract for ``policy`` and ``plan``. Raises ContractError; never partial."""
    entries = _parse_plan(plan)
    expected = set(policy.floors)
    for key in sorted(expected - set(entries)):
        raise ContractError(f"{key[0]}.{key[1]}: plan entry missing")
    for key in sorted(set(entries) - expected):
        raise ContractError(f"{key[0]}.{key[1]}: not in policy")

    columns: dict[str, dict[str, dict[str, Any]]] = {}
    released: dict[tuple[str, str], str] = {}  # (table, source column) -> release name
    tokens: list[dict[str, str]] = []
    for (table, column), entry in sorted(entries.items()):
        if entry["rung"] == _WITHHELD:
            continue
        name = output_column(entry)
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ContractError(f"{table}.{column}: release name")
        spec = columns.setdefault(table, {})
        if name in spec:
            raise ContractError(f"{table}.{name}: duplicate release name")
        form = _form(table, column, entry["rung"])
        params: dict[str, Any] = {"nullable": True, "rung": entry["rung"]}
        if name != column or entry["rung"].startswith("age."):
            params["derived_from"] = column
        spec[name] = {"form": form, "params": dict(sorted(params.items()))}
        released[(table, column)] = name
        if entry["rung"] == "id.pseudonym":
            scope = entry["params"].get("scope", _PSEUDONYM_SCOPE)
            if scope != _PSEUDONYM_SCOPE:
                raise ContractError(f"{table}.{column}: token scope invalid")
            tokens.append({"table": table, "column": name, "scope": scope})

    qi: list[dict[str, str]] = []
    for row in policy.qi:
        key = (row["table"], row["column"])
        if key not in expected:
            raise ContractError(f"{key[0]}.{key[1]}: qi not in policy")
        if key not in released:
            continue
        join = row.get("join_via")
        if join is not None:
            if not (isinstance(join, (list, tuple)) and len(join) == 2):
                raise ContractError(f"{key[0]}.{key[1]}: join_via")
            derived = f"join_{join[0]}_{join[1]}"
        else:
            derived = key[1]
        qi.append({"table": key[0], "column": released[key], "derived_from": derived})

    files = {
        f"{table}.csv": {"columns": dict(sorted(spec.items())), "required": sorted(spec)}
        for table, spec in sorted(columns.items())
    }
    contract = {
        "files": files,
        "qi": sorted(qi, key=lambda r: (r["table"], r["column"])),
        "tokens": sorted(tokens, key=lambda r: (r["table"], r["column"])),
    }
    _validate_contract(contract)
    return contract


def digest(contract: Mapping[str, Any]) -> str:
    """SHA-256 hex of the canonical contract (ticket 02's ``canonical_digest``)."""
    _validate_contract(contract)
    return canonical_digest(contract)


def _form(table: str, column: str, rung: str) -> str:
    try:
        form = contract_form(rung)
    except LadderError:
        raise ContractError(f"{table}.{column}: form missing for rung {rung}") from None
    if not _gate_form(form):
        raise ContractError(f"{table}.{column}: form invalid for rung {rung}")
    return form


def _gate_form(form: Any) -> bool:
    """A form ticket 04's gate understands: a validator ID or an anchored regex that compiles."""
    if not isinstance(form, str) or not form.strip() or len(form) > _FORM_MAX:
        return False
    if form in VALIDATOR_FORMS:
        return True
    if form.startswith("^") and form.endswith("$"):
        try:
            re.compile(form)
        except re.error:
            return False
        return True
    return False


def _parse_plan(plan: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    if isinstance(plan, (str, bytes)) or not isinstance(plan, Sequence):
        raise ContractError("plan: not a list")
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(plan):
        where = f"plan[{index}]"
        if not isinstance(raw, Mapping):
            raise ContractError(f"{where}: not an object")
        _exact(raw, _PLAN_KEYS, where)
        table, column, rung = raw["table"], raw["column"], raw["rung"]
        for label, value in (("table", table), ("column", column)):
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                raise ContractError(f"{where}: {label} name")
        if not isinstance(rung, str) or not rung:
            raise ContractError(f"{table}.{column}: rung")
        if not isinstance(raw["params"], Mapping):
            raise ContractError(f"{table}.{column}: params")
        key = (table, column)
        if key in entries:
            raise ContractError(f"{table}.{column}: duplicate plan entry")
        entries[key] = {"rung": rung, "params": dict(raw["params"]), "column": column}
    if not entries:
        raise ContractError("plan: empty")
    return entries


def _validate_contract(contract: Mapping[str, Any]) -> None:
    if not isinstance(contract, Mapping):
        raise ContractError("contract: not an object")
    _exact(contract, _CONTRACT_KEYS, "contract")
    files = contract["files"]
    if not isinstance(files, Mapping) or not files:
        raise ContractError("no released files")
    for name, spec in files.items():
        if not isinstance(name, str) or not _FILE.fullmatch(name):
            raise ContractError("contract: file name")
        if not isinstance(spec, Mapping):
            raise ContractError(f"{name}: not an object")
        _exact(spec, _FILE_KEYS, name)
        cols, required = spec["columns"], spec["required"]
        if not isinstance(cols, Mapping) or not cols:
            raise ContractError(f"{name}: columns")
        if not isinstance(required, list) or required != sorted(set(required)) or not set(required) <= set(cols):
            raise ContractError(f"{name}: required unsorted or undeclared")
        for column, body in cols.items():
            if not isinstance(column, str) or not _NAME.fullmatch(column):
                raise ContractError(f"{name}: column name")
            if not isinstance(body, Mapping):
                raise ContractError(f"{name}.{column}: not an object")
            _exact(body, _COL_KEYS, f"{name}.{column}")
            if not _gate_form(body["form"]):
                raise ContractError(f"{name}.{column}: form invalid")
            if not isinstance(body["params"], Mapping):
                raise ContractError(f"{name}.{column}: params")
    for label, keys in (("qi", _QI_KEYS), ("tokens", _TOKEN_KEYS)):
        rows = contract[label]
        if not isinstance(rows, list):
            raise ContractError(f"{label}: not a list")
        order = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ContractError(f"{label}: not an object")
            _exact(row, keys, label)
            if not all(isinstance(row[k], str) and row[k] for k in keys):
                raise ContractError(f"{label}: field")
            if not _NAME.fullmatch(row["table"]) or not _NAME.fullmatch(row["column"]):
                raise ContractError(f"{label}: name")
            order.append((row["table"], row["column"]))
        if order != sorted(set(order)):
            raise ContractError(f"{label}: unsorted")
    for row in contract["tokens"]:
        if row["scope"] not in _SCOPES:
            raise ContractError("tokens: scope")
    for row in contract["qi"]:
        if not _NAME.fullmatch(row["derived_from"]):
            raise ContractError("qi: derived_from")


def _exact(obj: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise ContractError(f"{where}: unknown key {min(unknown)}")
    missing = allowed - set(obj)
    if missing:
        raise ContractError(f"{where}: missing key {min(missing)}")
