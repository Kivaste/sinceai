---
status: accepted
---

# Merge the pattern engine with purpose-first framing

Two plans were already written, and they answer different questions. They are one product, not two.

## Context

[HACKATHON_PLAN.md](../../HACKATHON_PLAN.md) and [PRIVACY_PATTERNS_PLAN.md](../../PRIVACY_PATTERNS_PLAN.md) describe a scenario-driven PET compiler (S1), a free-text redactor (S2), and four proof patterns: keyed pseudonyms, a fail-closed gate, a privacy manifest, and fully offline. [concept.md](../concept.md) describes purpose-first release: start from the request, keep only what the scenario's tasks need, at the coarsest detail that still serves them. Building either plan alone would drop either the proof the judges score or the framing that differentiates us from "detect the column type, apply a PET".

## Decision

The two plan docs are the engine and the proof. Purpose-first is the framing, not a second pipeline. The scenario's required tasks decide what is released and at which detail; everything else is withheld; every field is justified. See D7.

## Alternatives considered

- **Purpose-first only, patterns later.** Rejected. The fail-closed gate, the manifest and offline operation are how we prove a release, not polish.
- **Patterns only, drop purpose-first.** Rejected. Without the purpose layer the tool is the obvious column-type pipeline, and withholding unused columns (the HEALTH-S1 story) has no rule behind it.
- **Keep both as competing plans.** Rejected. Tickets would not know which document wins when they disagree.

## Consequences

Specs and tickets trace each release decision to a scenario task (what may leave, and why) and to a pattern (how it is proved). Do not add a second pipeline. When the plans and the concept disagree, the concept decides *what* is released; the plans decide *how* it is protected and shown.
