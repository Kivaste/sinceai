"""Typed data dictionary: table and column names, roles, subtypes and descriptions. No data values.

This is the only description of the data that can reach an LLM prompt (ADR 0002).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pets_release.llm.screen import has_value_shape

MAX_DESCRIPTION = 300
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# Closed vocabularies from the kit taxonomy (role / subtype names, not values). Anything else fails closed.
ROLES = frozenset({"direct_identifier", "free_text", "non_sensitive", "quasi_identifier", "record_key",
                   "sensitive_attribute", "technical_identifier"})
SUBTYPES = frozenset({
    "ACCOUNT_ID", "AGE", "AGGREGATE", "BIRTH_DATE", "CARD_ID", "CATEGORY", "CUSTOMER_ID", "DATE", "DEVICE_ID",
    "DIAGNOSIS_CODE", "DURATION", "EDUCATION_DATA", "EMAIL", "EMPLOYEE_ID", "FINANCIAL_DATA", "FREE_TEXT",
    "GPS_COORDINATE", "HEALTH_DATA", "HOSTNAME", "IBAN", "IP_ADDRESS", "LANGUAGE", "LICENSE_PLATE",
    "LOCATION_NAME", "MAC_ADDRESS", "MEASUREMENT", "METER_ID", "MUNICIPALITY", "NATIONAL_ID", "OCCUPATION",
    "ORG_NAME", "OTHER", "PAYMENT_CARD", "PERSON_NAME", "PHONE", "POSTCODE", "PROPERTY_ID", "RECORD_ID", "SEX",
    "SOCIAL_DATA", "STREET_ADDRESS", "STUDENT_ID", "TIMESTAMP", "URL", "USERNAME", "USER_AGENT",
})
_H3 = re.compile(r"^###\s+(\S+)\s*/\s*(\S+)\s*$")
_H2 = re.compile(r"^##\s+(\S+)\s*$")
_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|(.*)\|\s*$")


class DictionaryError(ValueError):
    """The dictionary has no usable section for the dataset."""


@dataclass(frozen=True)
class ColumnInfo:
    """Value-free column metadata. Names, role and subtype are allowlisted (else DictionaryError);
    a description that looks like it carries a value is dropped to "" (documented in docs/llm-front-end.md)."""

    name: str
    role: str
    subtype: str
    description: str

    def __post_init__(self):
        if not (isinstance(self.name, str) and _NAME.match(self.name) and not has_value_shape(self.name)):
            raise DictionaryError("a column name is not a plain identifier")
        if self.role not in ROLES:
            raise DictionaryError("a column role is not in the closed role list")
        if self.subtype not in SUBTYPES:
            raise DictionaryError("a column subtype is not in the closed subtype list")
        desc = self.description if isinstance(self.description, str) else ""
        object.__setattr__(self, "description", "" if has_value_shape(desc) else desc[:MAX_DESCRIPTION])


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]

    def __post_init__(self):
        if not (isinstance(self.name, str) and _NAME.match(self.name) and not has_value_shape(self.name)):
            raise DictionaryError("a table name is not a plain identifier")


@dataclass(frozen=True)
class DataDictionary:
    dataset: str
    tables: tuple[TableInfo, ...]

    def __post_init__(self):
        if not (isinstance(self.dataset, str) and _NAME.match(self.dataset) and not has_value_shape(self.dataset)):
            raise DictionaryError("the dataset name is not a plain identifier")

    def columns(self) -> frozenset[tuple[str, str]]:
        return frozenset((t.name, c.name) for t in self.tables for c in t.columns)


def parse_dictionary(markdown: str, dataset: str) -> DataDictionary:
    """Parse the kit's docs/DATA_DICTIONARY.md for one dataset. Fails closed when nothing is found."""
    tables: dict[str, list[ColumnInfo]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        m = _H3.match(line)
        if m:
            current = m.group(2) if m.group(1) == dataset else None
            if current is not None:
                tables.setdefault(current, [])
            continue
        if _H2.match(line):
            current = None
            continue
        r = _ROW.match(line)
        if r and current is not None:
            cells = [c.strip() for c in r.group(2).split("|")]
            if len(cells) < 4:
                continue
            role, subtype, description = cells[0], cells[1], cells[-1]
            tables[current].append(ColumnInfo(r.group(1), role, subtype, description))
    populated = {n: cols for n, cols in tables.items() if cols}
    if not populated:
        raise DictionaryError("data dictionary has no tables for the requested dataset")
    return DataDictionary(dataset, tuple(TableInfo(n, tuple(populated[n])) for n in sorted(populated)))
