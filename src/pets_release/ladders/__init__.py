"""Detail ladders and pure transforms (ticket 07).

    from pets_release.ladders import apply, CONTRACT_FORMS, LADDERS, contract_form, output_column

``apply(plan, tables, keys, redactor=None) -> {table: DataFrame}`` applies a Plan
(``[{table, column, rung, params, floor, reason, source}]``) to string tables.
``keys`` needs only ``token(value, label="RECORD_KEY") -> 64-hex``; use
``PseudonymKeys(pseudonymiser, Scope.release(rsid))`` for ticket 06's pseudonymiser.

Rung IDs per ladder (finest first, ``withheld`` last) are in ``LADDERS``.
``CONTRACT_FORMS[rung]`` is the rung's contract form: an anchored regex ``^...$`` or
one of ``VALIDATOR_FORMS`` (``hex64 text integer decimal enum``). ``output_column(entry)``
gives the column name an entry produces (age rungs yield ``age_band``).

Null handling: a null or malformed source gives an empty cell on every rung, so contract columns
carry ``params.nullable: true`` (``contract_entry(rung)`` returns ``{form, params}``).
Every plan entry needs a valid ``floor`` (a rung ID or ``withheld``); else ``apply`` refuses.

Rung params: ``geo.topn {n}``; ``num.round {unit}``; ``num.bin {width, origin=0}``;
``age.band5|band10 {ref_column | ref_date, output="age_band"}``; ``id.pseudonym {label}``;
``lab.crp_other {ref_column="test_code", code="P-CRP"}`` (``CRP`` / ``other`` by the same row's lab code; D33).
"""

from .apply import DEFAULT_AGE_COLUMN, KeyMaterial, apply, output_column
from .keys import PseudonymKeys
from .rungs import (
    CONTRACT_FORMS,
    CONTRACT_PARAMS,
    LADDERS,
    RUNG_KIND,
    SACRIFICE_ONLY_RUNGS,
    VALIDATOR_FORMS,
    WITHHELD,
    LadderError,
    at_least_as_coarse,
    contract_entry,
    contract_form,
)

__all__ = [
    "CONTRACT_FORMS",
    "CONTRACT_PARAMS",
    "DEFAULT_AGE_COLUMN",
    "LADDERS",
    "RUNG_KIND",
    "VALIDATOR_FORMS",
    "WITHHELD",
    "KeyMaterial",
    "LadderError",
    "SACRIFICE_ONLY_RUNGS",
    "PseudonymKeys",
    "apply",
    "at_least_as_coarse",
    "contract_entry",
    "contract_form",
    "output_column",
]
