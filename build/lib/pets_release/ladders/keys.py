"""Adapter from ticket 06's pseudonymiser to the ``KeyMaterial`` seam used by ``apply``."""

from __future__ import annotations

from typing import Any


class PseudonymKeys:
    """``token(value, label)`` bound to one pseudonymiser and one scope (normally release scope).

    ``PseudonymKeys(pseudonymiser_for(master, recipient=...), Scope.release(rsid))``.
    Holds no key material itself and has no repr beyond its class name.
    """

    __slots__ = ("_p", "_scope")

    def __init__(self, pseudonymiser: Any, scope: Any) -> None:
        self._p = pseudonymiser
        self._scope = scope

    def token(self, value: str, label: str = "RECORD_KEY") -> str:
        return self._p.token(value, label=label, scope=self._scope)

    def __repr__(self) -> str:
        return "PseudonymKeys()"
