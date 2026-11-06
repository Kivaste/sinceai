# Evaluation strategy

Status: **proposed** (from the devil's-advocate review of the original "build the evaluators first" plan; see [build-plan.md](build-plan.md)).

## Principle: train, validation and test sets

If we optimise against a check, it stops being evidence. So checks are split by role:

| Check | Role | Used inside the minimise loop? |
|---|---|---|
| `pets-eval` public attackers + purpose checks + official utility tasks | **Training signal** | Yes |
| **Our own attacker** | **Validation** | **No.** Run only at milestones. |
| Organisers' hidden attackers (via `pets_submission/`) | **Final test** | Requested once, Saturday |

This guards against overfitting and gives a credible demo line: "verified by an attack our optimiser never saw."

## 1. Scoreboard (replaces "judge tooling")

A single command that runs every chosen scenario end to end and **appends one row per run** to a results table:

`timestamp, commit, scenario, each risk component (separately), worst risk, mean risk, privacy, utility, each purpose check, runtime`

- Track **each risk component separately**, never only the composite: the privacy score weights the *worst* risk at 50%, so the composite stalls while one risk dominates and hides real improvements elsewhere.
- Acts as a regression guard (did a change make anything worse?) and is the source of the before/after charts for the demo.

## 2. Our own attacker

- **Start it only once a real release exists**; designing attacks blind wastes time.
- Model it on the hidden attacker types the organisers named: **data broker, HR knowledge, colleagues, merchant, municipal insiders**. Pick the 2–3 that fit our lead dataset.
- Use the attacker knowledge in `adversary/` plus our own stronger assumptions (more known attributes, fuzzy matching, linkage across datasets, using the shared population).
- Measure the re-identification rate and attribute inference against `truth/`.
- Output: findings → new risks for the minimise loop to fix, and a "what still leaks" list for the honest-limitations slide.
- Time budget: about 25% of total effort, one person.

## 3. Mock judge (about 1 hour, Saturday evening)

- Grade our README, description, tagline and video script against the four published criteria (technical implementation, innovation, impact, presentation) and the five required demo items.
- Can be a checklist or an LLM review. Its job is to catch gaps, not to produce a score.

## 4. Ask instead of guessing

- Ask the TrustED experts on Discord what the company evaluators' criteria and weighting are.
- Show them an early release around Saturday midday and request the hidden-attacker run.

## Metrics we will report

- Risk components before vs after (direct identifiers, hashed-ID reversibility, k<5 share, linkage re-identification, free-text leakage, trajectory unicity, synthetic DCR / membership inference).
- Purpose-check and official-task scores before vs after.
- Alignment: generated purpose checks vs the official scenario tasks.
- Detection quality (`pets-eval detect`) vs the B1 baseline (macro-F1 0.65).
- Redaction quality (`pets-eval text`, F2) vs regex.
- Baselines to beat: `docs/BENCHMARK.md` in the package (B0 / B2 / B2-k per dataset and scenario).
