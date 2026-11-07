"""The one exact-type normaliser for every value that can reach the transport (body, URL, key header).

`type(x) is str` is checked before anything else, so no method of a `str` subclass (`strip`, `rstrip`,
`__format__`, `__eq__`, `__hash__`, `__str__`) is ever dispatched. Anything else is refused with a
content-free message (the field name only), so the call fails before the transport is reached (ADR 0002).
"""
from __future__ import annotations


def exact_text(value: object, what: str, error: type[Exception]) -> str:
    """Return a plain `str` copy of `value`, or raise `error` naming only the field."""
    if type(value) is not str:
        raise error(f"{what} is not plain text; refused before sending")
    return str.__str__(value)  # unbound str method: no dispatch on the argument's class
