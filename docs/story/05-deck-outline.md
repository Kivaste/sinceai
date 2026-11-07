# Deck draft: the five demonstration items (D40)

PREP, ten slides. Fill only after final review and fresh final-SHA proof. The
sources and full targets table are in 06. Screenshots for agents use hand-made
synthetic fixtures, never real-kit row views. No measured performance literals.

## 1. Data types and privacy risks

| Slide | Message | Visual / source |
|---|---|---|
| 1 | Purpose-First PETs: share only what the purpose needs | Name and tagline from 01; HEALTH-S1 recipient, controlled-research trust and purpose |
| 2 | Names are not the only linkage risk | Column roles from `inventory`; detector evidence shown separately if demonstrated; original privacy {{manifest.measured.privacy.components[component=privacy].before}} and below-k ROW share {{manifest.measured.privacy.components[component=k_below_5_share].before}}; attacker rates not measured unless manifest-backed |

## 2. PETs and why

| Slide | Message | Visual / source |
|---|---|---|
| 3 | Purpose checks justify each field and detail level | Data request → purpose checks → detail ladders → candidate release; `fieldJustifications`, `pets` |
| 4 | Keep necessary joins, withhold unnecessary detail | Keyed pseudonyms, generalisation, rounding and local suppression; actual rung and reason per field, not an obsolete hand plan |

<!-- IF #127 -->Slide 4 optional callout: process-pool scoring is opt-in; require
final-SHA byte-digest comparisons at multiple worker counts. No unmeasured speed-up.<!-- END IF -->

## 3. Protected output

| Slide | Message | Visual / source |
|---|---|---|
| 5 | Before-to-after is field-level, not raw rows | `date_of_birth` → `age_band`; exact band and time detail from final justifications; names and clinical_notes withheld; `contract` and `bindings.files` |

<!-- IF #117 -->Slide 5 human-only alternative: protected real-kit rows shown only
after display-time limited verify and matching manifest-file digests. Show the
exact D41 label: “Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment
only the recipient sees this view.” No raw input, row maps or truth/. Agents never
read or screenshot this real-kit view.<!-- END IF -->

## 4. Measured privacy and utility

| Slide | Message | Visual / source |
|---|---|---|
| 6 | Targets met / not met: privacy | 06's privacy rows, including minimum person-k {{manifest.measured.privacy.components[component=person_k.min].after}} and PERSON share below k {{manifest.measured.privacy.components[component=person_k.below_k_share].after}}; no age-band scorecard overclaim |
| 7 | Targets met / not met: utility and sacrifice | 06's task-by-task table, original 0.90 threshold vs enumerated floors; post-suppression scores; scorecard overall utility/composite not measured unless final manifest supplies keys |

<!-- IF #106 -->Slide 7 addition: the D33 test-name choice and its measured H-U7
effect, only if that choice is actually recorded in the final manifest.<!-- END IF -->

<!-- IF #24 -->Slide 8: CS-S1 per-label exact-match recall against 0.98. SECRET
remains unmet: {{manifest.residualRisks[risk=target-recall-secret].description}}.
Keep the original count/denominator and optimistic-later-result warning visible;
do not turn zero gate hits into a recall claim. State the accepted turn-level
template-held-out split. If D29 fallback was used, show withheld count, purpose-check
effect and reduced checker independence.<!-- END IF -->

## 5. Sharing scenario and limitations, then proof

| Slide | Message | Visual / source |
|---|---|---|
| 9 | Proof is scoped, and refusal is real | Exact final-SHA gate totals, not-applicable checks separately, actual limited and full verify outputs; synthetic planted-violation refusal through the real CLI; export assertion next to check/version/denominator/hits |
| 10 | Fit for a named purpose, not a promise of anonymity | Recipient/trust, `fitFor`, `notFitFor`, `sacrifices`, `residualRisks`; templated synthetic data; key custody; limited-verify tamper limitation; unmeasured risks remain not measured |

<!-- IF #32 -->Optional slide 10 future-work-to-shipped change: the request-only
LLM front end sees request text and dictionary, never rows. D39 go decision,
merged #32 and final-SHA proof are all required.<!-- END IF -->
