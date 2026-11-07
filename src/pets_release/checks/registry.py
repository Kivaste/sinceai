"""The single gate-check registry. Submodules of ``pets_release.checks`` register on import.

Discovery is fail closed: every discovered non-package submodule whose name does not start with
``_`` must register at least one check, and must import cleanly; otherwise ``all_checks()`` raises
``RegistryError`` and the runner refuses. Put helpers in ``_``-prefixed modules.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass

from pets_release.checks.records import SCOPES, UNITS, Outcome, Violation  # noqa: F401  (re-exported)

CHECK_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")  # ticket 02 schema: checkName
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")  # ticket 02 schema: version

# Manifest export-assertion key (ticket 02, camelCase) -> the one gate check whose record is its evidence.
# The writer (16) binds each assertion through this table. Producer/text entries are pinned here for
# tickets 11 and 05, which register those names.
ASSERTION_CHECKS = {
    "accountNumbers": "rescan.account-numbers",
    "deviceIds": "rescan.device-ids",
    "emails": "rescan.emails",
    "healthInText": "text.health",
    "ibans": "rescan.ibans",
    "ipAddresses": "rescan.ip-addresses",
    "keyMaterial": "producer.key-material",
    "nationalIds": "rescan.national-ids",
    "paymentCards": "rescan.payment-cards",
    "phones": "rescan.phones",
    "plates": "rescan.plates",
    "propertyIds": "rescan.property-ids",
    "quasiIdentifiersBelowK": "producer.person-k",
    "rawTimestamps": "rescan.raw-timestamps",
    "reversibleHashes": "producer.unkeyed-hashes",
    "rowMaps": "release.row-maps",
    "secrets": "rescan.secrets",
    "urlsWithTokens": "rescan.urls-with-tokens",
    "usernames": "rescan.usernames",
}


class RegistryError(Exception):
    """Raised when the registry cannot be trusted; message carries module/check names only."""


@dataclass(frozen=True)
class Check:
    name: str
    version: str
    scope: str
    unit: str
    run: Callable
    applies_to: tuple = ()  # contract column forms this check scans; required to return not_applicable


_CHECKS: dict[str, Check] = {}
_BY_MODULE: dict[str, int] = {}
_INFRA = {"records", "registry", "release", "runner", "__main__"}
_state: dict = {"loaded": False, "error": None}


def register(*, name: str, version: str, scope: str, unit: str, applies_to: tuple = ()):
    """Decorator: register ``run(release, contract, context) -> Outcome`` as a gate check.

    ``applies_to``: contract column forms (e.g. ``("text",)``) the check scans. Only a check that
    declares them may return ``Outcome.not_applicable()``, and only when the contract declares
    no column with any of those forms."""
    applies_to = tuple(applies_to)
    if not all(isinstance(f, str) and f for f in applies_to):
        raise RegistryError(f"bad applies_to for check {name!r}")
    if not isinstance(name, str) or not CHECK_NAME.match(name):
        raise RegistryError(f"bad check name {name!r}")
    if not isinstance(version, str) or not SEMVER.match(version):
        raise RegistryError(f"bad version for check {name!r}")
    if scope not in SCOPES or unit not in UNITS:
        raise RegistryError(f"bad scope or unit for check {name!r}")

    def deco(fn):
        if name in _CHECKS and _CHECKS[name].run is not fn:
            raise RegistryError(f"duplicate check name {name!r}")
        _CHECKS[name] = Check(name=name, version=version, scope=scope, unit=unit, run=fn, applies_to=applies_to)
        mod = getattr(fn, "__module__", "") or ""
        _BY_MODULE[mod] = _BY_MODULE.get(mod, 0) + 1
        return fn

    return deco


def _discover() -> None:
    if _state["error"] is not None:
        raise RegistryError(_state["error"])
    if _state["loaded"]:
        return
    import pets_release.checks as pkg

    found = sorted(pkgutil.walk_packages(pkg.__path__, prefix="pets_release.checks.",
                                         onerror=lambda n: _fail(f"cannot walk {n}")), key=lambda m: m.name)
    for mod in found:
        leaf = mod.name.rsplit(".", 1)[-1]
        if (mod.name.count(".") == 2 and leaf in _INFRA) or leaf.startswith("_"):
            continue
        try:
            importlib.import_module(mod.name)
        except Exception:  # noqa: BLE001  (record the module name only)
            _fail(f"check module {mod.name} failed to import")
        if not mod.ispkg and _BY_MODULE.get(mod.name, 0) == 0:
            _fail(f"check module {mod.name} registers no checks")
    _state["loaded"] = True


def _fail(msg: str):
    _state["error"] = msg
    raise RegistryError(msg)


def all_checks(scope: str | None = None) -> tuple[Check, ...]:
    """Every registered check, sorted by name; optionally only one verification scope."""
    _discover()
    return tuple(c for _, c in sorted(_CHECKS.items()) if scope is None or c.scope == scope)
