# The challenge

Sources: `Briefs/Challenge_TRUSTED_PETs_Transformer_EN (1) (1).pdf`, `Briefs/TrustED_PETs_Transformer_Challenge_Brief_FINAL_REVIEW (1).docx`, the package's `START_HERE.md` and `docs/`, and the public Since AI field guide (https://sinceai.ai/hackathon-2026/guide, builders and judges pages, updated 4 Nov 2026).

## The task

**TrustED PETs Transformer: protect the data, keep its value.** Build one **working tool** that:

1. **Detects** or classifies the types of data present.
2. **Selects** appropriate PETs for each data type and for the intended sharing scenario.
3. **Transforms** the dataset.
4. **Demonstrates** that the protected version stays useful for a defined analytical purpose.

The PETs named in the brief: masking, pseudonymisation, tokenisation, generalisation, binning, suppression, aggregation, synthetic data generation, free-text redaction, location precision reduction, timestamp rounding, and differential privacy for aggregate queries.

**The final demo must show:**
1. The data types identified.
2. The PETs selected for each data type.
3. The transformed dataset or protected view.
4. Utility before vs after.
5. The sharing scenario the protected data is fit for.

"The best solutions will not only hide sensitive values but also preserve the patterns, distributions, trends, relationships or indicators needed for the intended use case."

No specific dataset is mandated. The brief asks for one prototype and one realistic sharing scenario; covering everything is not required.

## Judging

| Who | When | How |
|---|---|---|
| **Company evaluators** (TrustED side) | Sun 10:00–13:00 | Review every submission to this challenge; pick the top three. Criteria are agreed privately ("to be confirmed" on the public page). |
| **Builder vote** | Sun 10:00–12:00 | Every builder makes 20 pairwise comparisons using **vote cards**: tagline, the first lines of the description, demo video, pitch deck, the first 5 "Built with" chips. No code or links. The top 5 across all challenges go to the finals. |
| **Overall jury** | Sun 14:00–15:10 | Finalists present live: ≤4 min pitch + ≤6 min Q&A. |

**Published criteria** (from the brief; no weights): (1) technical implementation, meaning correct, reliable PET choices; (2) innovation, meaning an intelligent, explainable approach; (3) impact, meaning evidence of reduced disclosure risk with preserved utility; (4) presentation, meaning a clear scenario, before/after comparison and honest limitations.

**Prizes per challenge:** €2,000 / €750 / €250. The overall winner gets €5,000.

## Submission (sinceai.app, not Devpost)

Required: project name (≤80 chars), tagline (≤140 chars, read first by voters), description (≤5,000 chars; judges read all, voters see the first lines), "Built with", repository link, **YouTube demo video (ideally under 2 min; show it working in the first 20 s)**, source zip ≤100 MB **without data files or dependencies**, MLH/GenAI questions, and terms accepted by every member.
Optional: demo URL, pitch deck, up to 2 supporting documents.

## Key times (EET)

| When | What |
|---|---|
| Fri 19:30 | Build starts |
| Sat 09:00–12:00, 14:30–18:00 | Partner Q&A. **TrustED answers remotely on Discord**, not at a stand. |
| **Sun 10:00** | **Hard submission deadline** |
| Sun 13:30 | Top three per challenge announced |
| Sun 14:00 | Finals |

## The data package (`Briefs/TRUSTED_PETS_PROVING_GROUND_2026 (1)/TRUSTED_PETS_PROVING_GROUND_2026/`)

- **One synthetic population** of 100k residents of Southwest Finland, shared across datasets, so cross-dataset linkage is a real risk.
- **Nine domain datasets** (`data/`): health, mobility, smart_city, energy, finance, cyber, education, public_admin, customer_service. Plus **`unseen`**: an HR export with obfuscated headers `c01..c26`, to be labelled without hints.
- **27 sharing scenarios** (`metadata/scenarios.json`, `docs/SCENARIOS.md`), each with a recipient, purpose, trust level (`public` / `contractual` / `controlled_research` / `internal`), threat model, legal context, required utility tasks and suggested privacy targets.
- **Attacker knowledge** (`adversary/`): 13 files (leaked lists, social posts, plate sightings, …). `truth/` maps records to people, for self-assessment.
- **`holdout/`**: non-member records for membership-inference tests on synthetic data.
- **`pets-eval` toolkit**: scorecard (privacy + utility + composite), detection scoring, free-text span scoring, residual-identifier check.
- **Baselines B0–B4** (`docs/BENCHMARK.md`, `results/`).

### Lessons stated in the package

- Dropping names isn't anonymisation. Under B0, a receipt (date, time, amount) still singles out 79% of the finance attacker's targets.
- Generalising without checking k leaves most rows unique. Enforcing k ≥ 5 fixes that, at a utility cost that depends on the scenario.
- Keyed pseudonyms keep joins. Random tokens break them.
- Regex misses names, spoken numbers and spelled-out emails. **"Free-text leakage is where most teams can win."**
- Differential privacy claims need ε, δ, the unit of privacy and the contribution bound.

### Rules

- Use only this synthetic data, public data, or data we're explicitly allowed to use.
- **Never publish `rowmap_*.csv`.** Keep `truth/` out of public materials.
- State the guarantee: "anonymised" and "differentially private" need a method and parameters.
- Licences: data CC BY 4.0, code MIT, © Since AI ry.

### Optional organiser checks

On request, put outputs in `pets_submission/` in our repo. The organisers can then run: (1) **stronger hidden attackers** for each domain (data broker, HR knowledge, colleagues, merchant, municipal insiders); (2) scoring of our `unseen` labels against private labels; (3) scoring of customer-service redaction on a hidden eval split.

## Organiser clarifications (public answers, Sat 7 Nov)

These are the organisers' answers to all teams, summarised. D40 records what they change for us.

- **Privacy technology vs practical value:** both count. Show what is protected, why the chosen methods fit, how useful the data stays, and how the results are measured.
- **One scenario or several:** neither is required, and covering more gives no automatic advantage. Judging uses the four published criteria (technical implementation, innovation, impact, presentation), not scenario count. Focus on quality and effectiveness.
- **Conflicting privacy and utility targets:** identifying and explaining the trade-offs is part of the challenge. Explain the decisions, show their impact with measurements, and be transparent about which targets are met, which aren't, and what limits remain. "The goal is not to claim perfect protection, but to demonstrate a well-reasoned and measurable approach."
- **Cloud-hosted or on-premise demo:** both are fine. Use synthetic, public or otherwise authorised data and follow sound security practice.
- **What every team must show:**
  1. identified data types and privacy risks;
  2. the PETs selected and the reasoning behind them;
  3. the transformed or protected output;
  4. measurable privacy and utility results;
  5. a clearly defined data-sharing scenario and its remaining limitations.
- **pets-eval:** its measurements support the demonstration but don't replace the official judging.
