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
An executable analysis, derived from a data request, that is answered on both the original and the released data to show the purpose is still served. A sharing scenario's required utility tasks are its purpose checks.
_Avoid_: test, utility metric

**Needs spec**:
The structured list of fields a data request requires, each with its level of detail and the reason it is needed.
_Avoid_: requirements, schema, field list

**Detail ladder**:
The ordered levels of detail a field can be released at, from exact down to withheld (e.g. timestamp → hour → day → week → withheld).
_Avoid_: hierarchy, granularity levels

## Source data

**Column role**:
What a source column is from a privacy point of view: direct identifier, quasi-identifier, sensitive attribute, technical identifier, free text, record key or non-sensitive.
_Avoid_: type, category, PII class

**Field inventory**:
The column role of every source column, each with the evidence that supports it.
_Avoid_: classification, profile, scan

**Span**:
A labelled stretch of free text that identifies or describes a person (a name, a spoken ID number, a health remark).
_Avoid_: entity, match, hit

## Release

**Release**:
What the tool hands to the recipient for one sharing scenario: the protected tables or views plus their privacy manifest.
_Avoid_: output, export, anonymised dataset

**Candidate release**:
A release that has been built but has not yet passed the gate; it is never visible to the recipient.
_Avoid_: draft, temp output

**Release form**:
The shape of a release: pseudonymised rows, aggregate tables, or synthetic data.
_Avoid_: format, output type

**Withheld**:
A field or table left out of a release because the data request does not need it.
_Avoid_: dropped, removed, suppressed (suppression means hiding individual values or rows, not whole fields)

**Pseudonym scope**:
The boundary within which the same original value always receives the same pseudonym: one conversation, one release, or one recipient. Across scopes, pseudonyms do not link.
_Avoid_: salt, namespace, key domain

**Placeholder**:
A typed, numbered pseudonym that replaces a span in free text (e.g. `[PERSON_1]`), consistent within its pseudonym scope.
_Avoid_: mask, tag, [REDACTED]

**Sacrifice**:
Utility deliberately given up for privacy, stated with the purpose check it affects and its score before and after.
_Avoid_: loss, degradation, cost

## Proof

**Release contract**:
The closed list, derived from a sharing scenario, of the files, columns and value forms a release may contain, and the columns it must contain.
_Avoid_: schema, allowlist, policy

**Gate**:
The independent check a candidate release must pass before it becomes a release; any high-severity violation refuses the whole release.
_Avoid_: validator, filter, linter

**Refusal**:
The outcome when a candidate release fails the gate: nothing is published, and a refusal report gives counts and locations but no values.
_Avoid_: error, failure, rejection

**Privacy manifest**:
The content-free record that accompanies a release: what was released at which detail and why, the PETs applied, risk and utility before and after, export assertions and residual risks.
_Avoid_: report, metadata, audit log

**Field justification**:
The recipient-readable reason, inside the privacy manifest, why a field is in a release at its chosen level of detail, or why it was withheld.
_Avoid_: rationale, explanation

**Export assertion**:
A privacy-manifest statement that a category of content (direct identifiers, secrets, key material, row maps…) is absent from a release; it can only state absence, and only after a named check has found zero occurrences in the release.
_Avoid_: flag, claim, guarantee

**Residual risk**:
A risk that remains in a published release and cannot be proven absent, stated with its measured rate.
_Avoid_: limitation, known issue, leak
