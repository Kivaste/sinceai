# Decision log

Append-only log kept by the orchestrator during execution. Do not rewrite or delete earlier entries; add a new one at the bottom.

This is not the planning snapshot. Current decisions are in [decisions.md](decisions.md). Hard-to-reverse trade-offs also have an ADR in [adr/](adr/).

Each entry records:

- **When** — time in EET
- **Decision** — what was decided
- **Why** — the reason, in a sentence
- **Evidence** — pointer to the artefact (a file, a release folder, a `pets-eval` run)

## Entries

### Sat 00:15 — planning interview complete; see docs/decisions.md D6–D17

- **When:** Sat 00:15 EET
- **Decision:** Planning interview complete; see [docs/decisions.md](decisions.md) D6–D17.
- **Why:** Lock team, scope, stack, process and checkpoints before spec and tickets.
- **Evidence:** [docs/decisions.md](decisions.md) D6–D17; ADRs [0001](adr/0001-merge-pattern-engine-with-purpose-first-framing.md), [0002](adr/0002-llm-never-sees-data-values.md), [0003](adr/0003-row-maps-only-in-separate-private-repo.md).
