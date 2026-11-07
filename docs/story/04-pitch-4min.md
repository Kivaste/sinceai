# Four-minute pitch and six-minute Q&A draft

PREP. Five beats follow D40, not feature count. All measurements come from the
final-SHA manifests under 06's source rules. No final text is created yet.

## 1. Data types and privacy risks (0:00–0:40)

“A hospital needs to share emergency-visit data with a university research group
studying crowding and revisits. Removing names leaves ages, places, timestamps and
joins. Our field inventory records the column roles and their evidence.”

Show the detector separately from the release inventory: a policy-derived inventory
is not evidence that the detector measured those roles. Original scorecard privacy:
{{manifest.measured.privacy.components[component=privacy].before}}. Below-k ROW
share before protection:
{{manifest.measured.privacy.components[component=k_below_5_share].before}}. Attacker
persona rates and a full k histogram: not measured unless supplied by the final
manifest. A scorecard linkage component is not both attacker personas.

## 2. PETs and why (0:40–1:20)

“The data request becomes purpose checks. Withholding avoids sharing unneeded
fields. Keyed pseudonyms preserve required joins; generalisation and local
suppression reduce quasi-identifier detail. Each field justification names the
chosen rung, ladder floor and reason.”

Show `pets`, `fieldJustifications` and purpose checks together. Read actual rungs
and parameters, not an old hand plan. A bounded detail-ladder search is not proof
of a global optimum or that every original utility threshold was met.

<!-- IF #127 -->“Parallel search scoring is opt-in. We require byte-identical
releases at each worker count and fail closed on a failed worker.” Demonstrate
only if final-SHA runs verify those claims; do not invent a speed-up.<!-- END IF -->

## 3. Protected output (1:20–1:55)

Show field-level before-to-after changes from `fieldJustifications`: birth date
to `age_band`, names and `clinical_notes` withheld, required join keys pseudonymised.
<!-- IF #106 -->Show D33's lab test-name decision exactly as the final manifest records it: a
coarsened distinction for H-U7 if adopted, or an explicitly justified threat-model
exception in residual risks. Do not assert that a pending policy change shipped.
<!-- END IF -->

<!-- IF #117 -->The human can show protected real-kit rows only through the web
app's display-time limited verify and matching manifest-file digests. Label:
“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient
sees this view.” No raw input, row maps or truth/. Agents never inspect or
screenshot the real-kit row view; synthetic fixtures only.<!-- END IF -->

## 4. Measured privacy and utility (1:55–3:10)

Display the full targets met / not met table from 06. Show original thresholds
beside policy sacrifice floors, and post-suppression purpose-check scores.
Independent per-person minimum k:
{{manifest.measured.privacy.components[component=person_k.min].after}}; PERSON
share below k:
{{manifest.measured.privacy.components[component=person_k.below_k_share].after}}.
Scorecard privacy after:
{{manifest.measured.privacy.components[component=privacy].after}}. Disclose its
renamed-`age_band` blind spot. Overall scorecard utility and composite: not measured
in the current manifest; never substitute baseline utility or composite scores.

<!-- IF #24 -->“CS-S1 is a different sharing scenario: contact-centre turns to an
external LLM analytics vendor, with conversation-scoped placeholders. Each target
label needs exact-match recall of 0.98. SECRET is an unmet target.”

Read the complete per-label target note:
{{manifest.residualRisks[risk=target-recall-secret].description}}.
The note carries the pre-change count and denominator; later results are optimistic
because held-out misses informed the redactor change. Show the accepted turn-level
template-held-out split, not a claim of untouched conversation-held-out evaluation.
Show NATIONAL_ID, PAYMENT_CARD and IBAN separately; no combined-score substitute.
Any D29 fallback must show withheld-turn counts and the utility effect, and disclose
reduced checker independence. A strict gate pass does not erase unmet recall.<!-- END IF -->

## 5. Sharing scenario and limitations, then proof (3:10–4:00)

“The release serves these purpose checks for this recipient and trust level, not
individual care or arbitrary reuse. Pseudonymised data is still personal data.
The data is synthetic and templated. Unmeasured risks are not zero.”

Show final manifest `fitFor`, `notFitFor`, `sacrifices`, `residualRisks`; then the
actual gate N/N (list not-applicable checks separately), fresh limited verify and
fresh full verify outcomes on the final SHA. Show a deliberate synthetic refusal
through the real CLI, with check name and counts only. Never reuse an old green
line. Limited verify cannot authenticate the HMAC signature; full verify needs the
controller's inputs and key. “Share only what the purpose needs.”

<!-- IF #32 -->“The optional front end turns request text and the data dictionary
into a needs spec; it never sees row values.” Keep only after the D39 go decision
and final-SHA proof. Otherwise describe it solely as future work.<!-- END IF -->

## Jury Q&A

| Question | Honest answer |
|---|---|
| Does a passed gate mean anonymity? | No. Assertions cover named checks and labels only; residual risks remain. Pseudonymised data is personal data. |
| Which targets did you miss? | Read 06's final table. An accepted policy sacrifice is not a full pass at the original utility threshold; unavailable values say not measured. |
| Can the recipient verify everything? | No. Limited verify re-runs release-scope checks; producer-scope checks, signature and inputs require full verify with the controller's key. |
| Does the scorecard prove attack resistance? | No. Its renamed-age-band blind spot is disclosed; person-k and row-k are distinct. Both attacker-persona rates must be measured separately or say not measured. |
| What if the gate misses a name? | Low-severity text labels have residual risks, not universal absence assertions. Known coverage gaps and the evaluation frame stay visible. |
| Is the processing offline? | The release engine blocks network access; do not confuse an optional request-only front end with transmitting rows. Same inputs, key, creation time and versions must produce identical bytes; demonstrate rather than assert a new run passed. |
| What remains future work? | Unmerged or unverified optional features, broader sharing scenarios and generalisation beyond templated synthetic data. |

<!-- IF #24 -->SECRET Q&A: the original held-out result is an unmet target against
0.98. Quote {{manifest.residualRisks[risk=target-recall-secret].description}} rather
than replacing it with a later optimistic score. Independent gate zero hits is a
separate bounded check, not recall proof.<!-- END IF -->
