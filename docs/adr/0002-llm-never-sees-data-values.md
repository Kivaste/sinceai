---
status: accepted
---

# An LLM never sees data values

No model call is on the v1 path. If a later stretch adds one, it may see the request and the data dictionary only.

## Context

The hybrid architecture (D3) had an LLM turn a plain-language request into a needs spec. Putting row values in that prompt would break the offline pattern, the AGENTS.md rule that values stay local, and the story we tell the jury. A model outage or a slow key must not block submission.

## Decision

No LLM in v1. The Sat 14:00 go/no-go may add a stretch step: request text + data dictionary → needs spec. That step never receives data values. The provider is user-configurable (API key / endpoint). Suggested default is a local or self-hosted OpenAI-compatible endpoint; Mistral is the second suggestion. See D9.

## Alternatives considered

- **Cloud LLM with rows in the prompt.** Rejected. Values must not leave the machine, and it contradicts pattern P4 (fully offline).
- **LLM on the v1 critical path, dictionary only.** Rejected for v1. The measured search (D10) can run on the official tasks without it. A missing key would stop the demo.
- **No LLM, ever.** Not chosen. A plain-language request is still the purpose-first front door; it stays a timed stretch, not a promise.

## Consequences

v1 needs specs are taken from the scenario tasks, not generated. Any later client must be built so row values cannot be passed in: the call site sees request text and the dictionary, nothing else. Schema names and aggregate metrics may be discussed with a model; cell values may not. NER, if the Sat 12:00 go/no-go allows it, is an optional extra (D11), under the same rule.
