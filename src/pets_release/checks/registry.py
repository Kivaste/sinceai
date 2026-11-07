"""The single gate-check registry. Submodules of ``pets_release.checks`` register on import."""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

from pets_release.checks.records import SCOPES, UNITS, Outcome, Violation  # noqa: F401  (re-export)


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    version: str
    scope: str
    unit: str
    run: Callable


_CHECKS: dict[str, Check] = {}
_INFRA = {"records", "registry", "release", "runner", "__main__"}
_loaded = False


def register(*, name: str, version: str, scope: str, unit: str):
    if scope not in SCOPES or unit not in UNITS or not name or not version:
        raise RegistryError(f"bad registration for check {name!r}")

    def deco(fn):
        if name in _CHECKS and _CHECKS[name].run is not fn:
            raise RegistryError(f"duplicate check name {name!r}")
        _CHECKS[name] = Check(name=name, version=str(version), scope=scope, unit=unit, run=fn)
        return fn

    return deco


def _discover() -> None:
    global _loaded
    if _loaded:
        return
    import pets_release.checks as pkg

    for mod in sorted(pkgutil.walk_packages(pkg.__path__, prefix="pets_release.checks."), key=lambda m: m.name):
        leaf = mod.name.rsplit(".", 1)[-1]
        if mod.name.count(".") == 2 and leaf in _INFRA:
            continue
        if leaf.startswith("_") and leaf != "__init__":
            continue
        importlib.import_module(mod.name)
    _loaded = True


def all_checks(scope: str | None = None) -> tuple[Check, ...]:
    """Every registered check, sorted by name; optionally only one verification scope."""
    _discover()
    return tuple(c for _, c in sorted(_CHECKS.items()) if scope is None or c.scope == scope)
