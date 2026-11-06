# Decisions and open questions

Updated as decisions are made. The planning map (wayfinder) will live on the issue tracker once Q3 is answered; this file is the snapshot.

## Decided

| # | Decision | Detail |
|---|---|---|
| D1 | **GitHub repo** | Private, `Kivaste/sinceai`, `origin` set, branch `main`. Nothing committed yet. |
| D2 | **Purpose-first angle** | Start from the data request (business need), release only what's needed, at the coarsest detail that serves it. See [concept.md](concept.md). |
| D3 | **Tool architecture: option D (hybrid)** | LLM turns the request into a needs spec + purpose checks → measured search tightens each field to the minimum → verification. Build the search on the official tasks first (C), then put the LLM step in front (B). See [tool-spec.md](tool-spec.md). |
| D4 | **Scope** | One tool; one lead dataset and scenario demonstrated in depth; nothing mandates using all datasets. |
| D5 | **Vocabulary** | [GLOSSARY.md](../GLOSSARY.md) is the source of the project's terms. |

### Options considered for D3

| Option | Verdict |
|---|---|
| A. Fixed lookup of needs per scenario | Rejected: a config, not a tool |
| B. LLM reads the request | Kept as the front end; can't be checked on its own |
| C. Measured search over detail ladders | Kept as the engine and the fallback demo |
| **D. B → C hybrid** | **Chosen** |

## Proposed (awaiting confirmation)

| # | Proposal | Where |
|---|---|---|
| P1 | Skeleton-first build order; the loop lives inside the product, not as a dev-time process | [build-plan.md](build-plan.md) |
| P2 | Checks split into training (`pets-eval`), validation (our attacker), test (hidden organiser attackers) | [evaluation-strategy.md](evaluation-strategy.md) |
| P3 | Scoreboard instead of "judge tooling"; mock judge as a 1-hour task | [evaluation-strategy.md](evaluation-strategy.md) |
| P4 | Checkpoints: skeleton Fri 23:00, show TrustED Sat 12:00, freeze Sat 20:00, submit Sun 08:00 | [build-plan.md](build-plan.md) |

## Open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | **Destination of the planning map**: does it end at a build spec, with building outside the map? | Yes |
| Q2 | **Attacker time budget**: about 25% of build time, one person, 2–3 attacker types fitted to the lead dataset? | Yes |
| Q3 | **Where the planning map lives**: GitHub Issues on `Kivaste/sinceai`? | Yes |
| Q4 | **Team**: how many people, which skills, everyone using an AI coding agent? | Needed to assign workstreams and decide CLI + HTML vs web UI |
| Q5 | **Lead dataset and scenario** | Not yet discussed. Weigh: room above the baselines, how well purpose-first shows, data size, free-text opportunity. |
| Q6 | **LLM**: which model and hosting; cost; offline fallback | Not yet discussed |
| Q7 | **Purpose-check representation**: generated code vs a fixed vocabulary of analysis types | Leaning towards the vocabulary (safer, easier to validate) |
| Q8 | **Acceptance threshold** for purpose checks (e.g. ≥ 0.9) | Not yet discussed |
| Q9 | **Report/UI format** | Depends on Q4 |
| Q10 | **`unseen` dataset**: do we submit labels for the organiser check? | Cheap if our detector is general; decide after the skeleton |
| Q11 | **Questions for TrustED on Discord** (criteria and weighting, the hidden-check process) | Draft once the plan is confirmed |
