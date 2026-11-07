"""Prompt builder. Takes the request text, a typed DataDictionary and the vocabulary; nothing else.

There is no parameter that can carry a table or a cell value. Any other type is refused.
"""
from __future__ import annotations

import json

from pets_release.llm.dictionary import DataDictionary
from pets_release.llm.vocabulary import DETAIL_LEVELS, TRUST_LEVELS, AnalysisType

SYSTEM = (
    "You draft a data-sharing policy from a plain-language data request. You are given the request, "
    "a data dictionary (table and column names with role and subtype) and a fixed list of analysis types. "
    "You never see data. Answer with one JSON object and nothing else, with exactly these keys: "
    '"recipient" (string), "trustLevel" (one of {trust}), '
    '"purposeChecks" (list of {{"id": <analysis id from the list>, "reason": string}}), '
    '"fieldsNeeded" (list of {{"table": string, "column": string, "detail": one of {detail}, '
    '"reason": string}}). Use only table and column names from the dictionary and only analysis ids from the list. '
    "Ask for the least detail the analyses need."
)


def build_messages(request: str, dictionary: DataDictionary, vocabulary: tuple[AnalysisType, ...]) -> list[dict]:
    if not isinstance(request, str):
        raise TypeError("request must be text")
    if not isinstance(dictionary, DataDictionary):
        raise TypeError("dictionary must be a DataDictionary")
    if not isinstance(vocabulary, tuple) or not all(isinstance(a, AnalysisType) for a in vocabulary):
        raise TypeError("vocabulary must be a tuple of AnalysisType")
    dictionary = dictionary.validated()  # fresh copy from real instances only; re-runs the allowlists
    schema = {
        "dataset": dictionary.dataset,
        "tables": [
            {
                "name": t.name,
                "columns": [{"name": c.name, "role": c.role, "subtype": c.subtype} for c in t.columns],
            }
            for t in dictionary.tables
        ],
    }
    analyses = [{"id": a.id, "description": a.description} for a in vocabulary]
    user = (
        f"Data request:\n{request}\n\nData dictionary:\n{json.dumps(schema, sort_keys=True)}\n\n"
        f"Analysis types:\n{json.dumps(analyses, sort_keys=True)}"
    )
    system = SYSTEM.format(trust=list(TRUST_LEVELS), detail=list(DETAIL_LEVELS))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
