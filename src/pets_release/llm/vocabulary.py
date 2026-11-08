"""The fixed vocabulary of analysis types a draft may name.

Every entry is a purpose-check ID that the packaged scenario policies already understand
(`pets_release.policy`); a test pins the table to those policies. Descriptions are the kit's
task descriptions (schema-level text, no data).
"""
from __future__ import annotations

from dataclasses import dataclass

TRUST_LEVELS = ("public", "contractual", "controlled_research", "internal")
DETAIL_LEVELS = ("exact", "pseudonymised", "generalised", "redacted", "aggregate")


@dataclass(frozen=True)
class AnalysisType:
    id: str
    dataset: str
    description: str


ANALYSIS_TYPES: tuple[AnalysisType, ...] = (
    AnalysisType("H-U2", "health", "Median length of stay by triage level"),
    AnalysisType("H-U4", "health", "Diagnosis-group mix in the eight largest municipalities"),
    AnalysisType("H-U6", "health", "30-day revisit rate by age band"),
    AnalysisType("H-U7", "health", "CRP vs temperature relationship and CRP by diagnosis group (needs visit join)"),
    AnalysisType("H-U8", "health", "Hour-of-day arrival curve"),
    AnalysisType("CS-U1", "customer_service", "Intent classifier trained on protected text, tested on original text"),
    AnalysisType("CS-U3", "customer_service", "Contact-reason (intent) mix preserved"),
    AnalysisType("CS-U4", "customer_service", "Average handle time by intent"),
    AnalysisType("CS-U5", "customer_service", "Ordinary vocabulary retained in text"),
)


class VocabularyError(ValueError):
    pass


def vocabulary_for(dataset: str) -> tuple[AnalysisType, ...]:
    """The analysis types offered for a dataset; an unsupported dataset fails closed."""
    found = tuple(a for a in ANALYSIS_TYPES if a.dataset == dataset)
    if not found:
        raise VocabularyError("no analysis types are defined for this dataset")
    return found
