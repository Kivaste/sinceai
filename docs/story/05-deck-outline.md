# Deck outline: the five demonstration items (D40)

**FINAL at c52424c (merged to main cc66ac2)**.
Ten slides. Final-release sources are in PRE-FILL-SOURCES and
the full targets met / not met table in 06. Agent screenshots use hand-made
synthetic fixtures, never real-kit row views. Measurements bind the release pin,
not this later docs commit; this outline does not certify a recorded demonstration.

## 1. Data types and privacy risks

| Slide | Message | Visual / source |
|---|---|---|
| 1 | sinceai: self-hosted pipeline engine | Library/CLI in CI, Airflow or dbt; web app = approval and audit console; HEALTH-S1, controlled-research trust and purpose; REST API future work |
| 2 | Names are not the only linkage risk | Column roles from `inventory`; detector evidence shown separately if demonstrated; original privacy 0.1716, below-k=5 ROW share 0.9557 and linkage 0.5697; measured persona and red-team rates in 06 |

## 2. PETs and why

| Slide | Message | Visual / source |
|---|---|---|
| 3 | Purpose checks justify each field and detail level | Data request → purpose checks → detail ladders → candidate release; `fieldJustifications`, `pets` |
| 4 | Keep necessary joins, withhold unnecessary detail | Keyed pseudonyms, generalisation, rounding and local suppression; actual rung and reason per field, not an obsolete hand plan |

Slide 4 note: bounded search optimises k and purpose-check utility, not attacker
rates. Attacker measurements are post-hoc. No speed-up measured by this run.

## 3. Protected output

| Slide | Message | Visual / source |
|---|---|---|
| 5 | Before-to-after is field-level, not raw rows | `date_of_birth` → `age_band`; exact band and time detail from final justifications; names and clinical_notes withheld; `contract` and `bindings.files` |

Slide 5 human-only alternative: protected real-kit rows shown only
after display-time limited verify and matching manifest-file digests. Show the
exact D41 label: “Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment
only the recipient sees this view.” No raw input, row maps or truth/. Agents never
read or screenshot this real-kit view.

## 4. Measured privacy and utility

| Slide | Message | Visual / source |
|---|---|---|
| 6 | Targets met / not met: privacy | Privacy 0.1716 → 1.0; linkage 0.5697 → 0; below-k=5 ROW share 0.9557 → 0. Person-k minimum 5 and below-k PERSON share 0 across 24,204 persons, on both QI sets; no age_band scorecard overclaim |
| 7 | Targets met / not met: utility and sacrifice | Mean of five tasks 1.0 → 0.9188. H-U2/H-U4/H-U6/H-U7/H-U8: 0.9195/0.7952/0.9462/0.9827/0.9504. H-U2 30-minute-bin detail sacrifice still meets 0.90; H-U4 misses 0.90 but meets floor 0.6. No composite claim |

Slide 7 addition: `lab_results.test_name` is withheld, H-U7 0.9827. Exact
`test_code` preserves test identity; test-history linkage remains a residual risk.
Both D58 QI sets are measured (#146), with withheld-column justifications.
Diagnosis-known below-k=5 person share is 73.6% (#143), a residual risk beyond
the declared QIs. Recipients need the key holder for full k verification.

Slide 8: component diagnostics, not a perfect-privacy headline. The scorecard
misses renamed age_band. Measured persona rates and red-team results are separate:
0 unique red-team re-identifications in the tested frames, not universal safety.
Population inference lift: icd10_primary 2.1351x, no bound (chapter-level coding
makes H-U4 0); los_minutes 1.6894x, enforced bound 2.0x (#157, D64). Distinguish
these from sampled attacker rates. CS-S1 is future work under D46, with a
strict-gate refusal, not a released scenario. Its evaluation uses typed, numbered
placeholders and D37 masking, never realistic fake values.

## 5. Sharing scenario and limitations, then proof

| Slide | Message | Visual / source |
|---|---|---|
| 9 | Proof is scoped | Final gate: 42 checks, 42 pass, 0 not applicable; release and both verify tiers exit 0 (PRE-FILL-SOURCES). A fresh synthetic refusal is not demonstrated by this measured proof. Publish only on exit 0 plus successful verification; either nonzero exit stops. |
| 10 | Fit for a named purpose, not a promise of anonymity | Recipient/trust, `fitFor`, `notFitFor`, `sacrifices`, `residualRisks`; templated synthetic data; key custody; limited-verify tamper limitation; unmeasured risks remain not measured |

Slide 10 evidence handoff (D60): evidence-pack exporter available and pack exists (#147).
Its DPO/Findata-shaped purpose, method/parameters, attacker risk, utility, residual
risks and reproducibility must come from the authenticated signed manifest only.
Legal basis and DPIA: to be supplied by the controller. Source rows and keys stay
in-house. The optional Mistral LLM front end drafts a validated purpose-first policy from
request and schema information only (never row values) for human review; feeding
the draft into the search is future work.
