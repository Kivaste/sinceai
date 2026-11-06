# Build plan

Status: **proposed**. Team size and roles are still open (see [decisions.md](decisions.md)), so the workstreams are not yet assigned.

## How we got here

The original idea was: (1) build judge-evaluation and attack tooling first, then (2) run an automated loop that tries PET methods and keeps any change that improves privacy while keeping utility. A devil's-advocate review found these problems:

| Problem | Why it matters |
|---|---|
| Evaluation first leaves no product until late | ~38 h total; a strong demo needs a working product early |
| "Judge tooling" can't be faithful | Criteria are private; the judges are people reading text and watching video |
| Attacker built before any release is designed blind | We don't yet know what will leak |
| Optimising against our own checks overfits | The hidden organiser attackers will find what we tuned around |
| The composite score stalls the loop | Worst risk is weighted 50%; other improvements get discarded |
| Greedy one-change-at-a-time search misses interactions | k-anonymity is joint over quasi-identifiers; the result depends on the order of changes |
| "Utility roughly the same" isn't a rule | Two objectives need an explicit acceptance rule |
| The result is a tuned config, not a tool | Weak against "intelligent, explainable approach" |
| The loop doesn't fit detection or redaction | Those are model-quality problems, scored on precision and recall |

What the original idea got right: **a measured loop is the core of a good solution.** So the loop moves **into the product** (the minimise step of [tool-spec.md](tool-spec.md)), and evaluation is split into training, validation and test checks ([evaluation-strategy.md](evaluation-strategy.md)).

## Sequencing

1. **End-to-end skeleton first.** Request → needs spec (hard-coded at first) → transform → `pets-eval` → report, for one scenario. Everything after this improves something that already runs.
2. **Thicken in this order:** minimise search on the official scenario tasks (option C) → LLM understand step in front of it (option B) → better detection → better free-text redaction → report and UI.
3. **Attacker track** starts from the first real release and runs in parallel (one person, about 25%).
4. **Scoreboard** from day one, as soon as the skeleton exists.
5. **Fallback:** if the LLM step is unreliable by Saturday evening, demo option C on the official scenario tasks; that is still a complete story.

## Checkpoints (EET)

| When | Checkpoint |
|---|---|
| Fri ~23:00 | Skeleton runs end to end for the lead scenario; scoreboard writes its first row |
| Sat 12:00 | Working release shown to the TrustED experts on Discord; hidden-attacker check requested |
| Sat ~20:00 | **Feature freeze** |
| Sat night | README, submission description, tagline, video recorded, mock-judge pass |
| Sun 08:00 | **Submit** (buffer before the fixed 10:00 deadline) |

## Workstreams (to assign once the team is known)

| Stream | Scope |
|---|---|
| Core pipeline | Transform, ladders, minimise search, release writer, scoreboard |
| Understand (LLM) | Request → needs spec + purpose checks, schema validation, alignment with official tasks |
| Detect + redact | Column-role detection, free-text redaction, `pets-eval detect` / `text` scoring |
| Attacker | Our own attacker (validation), findings to the loop and the limitations slide |
| Story | Report/UI, demo script, video, description, deck |

## Risks

| Risk | Mitigation |
|---|---|
| LLM produces wrong or over-broad needs | Strict schema, validation against the dictionary, human approval, alignment score against the official tasks |
| Search is too slow on big tables | Sample in the loop, full run at the end; pick a lead dataset of manageable size |
| Overfitting to public attackers | Training/validation/test split; request the hidden check |
| Scope creep | One lead scenario in depth plus one more to show generalisation; feature freeze Sat 20:00 |
| Secrets or rowmaps leak into the repo | `.gitignore` before the first commit; HMAC key from an env var |
| Late submission | Submit at 08:00 Sunday; video done Saturday night |
