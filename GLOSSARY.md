# Purpose-first PETs

A tool that starts from what a data recipient needs, releases only that, at the coarsest detail that still serves the purpose, and proves both the privacy and the utility of the result.

## Request and needs

**Data request**:
A plain-language statement of who wants the data and what they want to learn from it.
_Avoid_: query, ask, use case

**Sharing scenario**:
A data request with its recipient, trust level, threat model and legal context fixed; the challenge package ships 27 of them.
_Avoid_: use case, setting

**Purpose check**:
An executable analysis, derived from a data request, that is answered on both the original and the released data to show the purpose is still served.
_Avoid_: test, utility metric

**Needs spec**:
The structured list of fields a data request requires, each with its level of detail and the reason it is needed.
_Avoid_: requirements, schema, field list

**Detail ladder**:
The ordered levels of detail a field can be released at, from exact down to withheld (e.g. timestamp → hour → day → week → withheld).
_Avoid_: hierarchy, granularity levels

## Release

**Release**:
What the tool hands to the recipient for one data request: the transformed tables or views, plus the field justifications.
_Avoid_: output, export, anonymised dataset

**Release form**:
The shape of a release: pseudonymised rows, aggregate tables, or synthetic data.
_Avoid_: format, output type

**Withheld**:
A field or table left out of a release because the data request does not need it.
_Avoid_: dropped, removed, suppressed (suppression means hiding individual values or rows, not whole fields)

**Field justification**:
The recipient-readable reason a field is in a release at its chosen level of detail, or why it was withheld.
_Avoid_: rationale, explanation
