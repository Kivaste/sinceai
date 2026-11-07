# Final-SHA sources, targets met / not met, and claim gates

**PREP only (#103).** No final submission folder or final measurements yet. Every
earlier story-kit release, including the old e846512 run, is historical: a new
commit invalidates its evidence, even if it changes only docs. Do not reuse its
numbers, gate totals or verify success lines. Finalisation waits for final review
and fresh proof bound to the exact final SHA and inputs.

## Source contract: actual manifest keys, not guessed paths

All `{{manifest.<path>}}` expressions address a single scenario's
`privacy_manifest.json`. The default in 01–05 is HEALTH-S1; **inside a #24 block
the default is CS-S1**. Tables below name the scenario explicitly. This namespace
is an editing convention, not a field named `manifest` in the JSON.

Use direct keys with explicit array selectors: `tasks[task=H-U2].after` means the
unique `tasks` entry whose `task` equals `H-U2`; `components[component=person_k.min]`
matches the entire component ID, including the dot. Multiple selectors, separated
by commas, must all match one entry. Zero or multiple matches are unresolved, never
zero. No implicit list index, guessed alias, list `.count` field, or interpolation
from a different scenario. This is a manual finalisation contract, **not supported
by the older `docs/story-kit/fill_numbers.py` resolver**.

Authoritative code inspected at the prep base `f98cf626e1b7edf104fecbee1602b2f91cef3a8c`:

| Source | Actual keys / meaning |
|---|---|
| `src/pets_release/manifest/schema.py`, `_MEASURED` | `measured.utility.tasks[].{task,status,before,after}`, `measured.privacy.components[].{component,before,after}`, `measured.redaction.labels[].{label,tp,fp,fn,support,precision,recall}` |
| Same schema, top-level records | `inventory`, `pets[].{table,column,pet,params}`, `fieldJustifications[].{table,column,outputColumn,decision,rung,floor,reason,source}`, `contract.k`, `contract.files`, `bindings.files`, `bindings.toolRevision` |
| Same schema, evidence and risks | `assertionEvidence.<name>.{check,version,scope,status,denominator,hits}`, `gate.{status,checks}`, `residualRisks[].{risk,kind,label,rate,description}`, `sacrifices[].{check,floor,before,after,reason}` |
| `src/pets_release/writer/assemble.py` | `assemble_manifest` copies the narrative, derives assertions only from their required checks, copies gate records and binds `bindings.toolRevision` and inputs; it does not invent measurement fields |
| `src/pets_release/run/narrative.py` | Writes local suppression under `pets[pet=local_suppression].params.{k,maxShare,unitsSuppressed,share}`; sacrifice floors; risk IDs `free-text-recall`, `linkage-attackers`, `attribute-inference` |
| `src/pets_release/measure/ids.py`, `core.py`, `k.py` | Actual component IDs `privacy`, `k_below_5_share`, `linkage_reid`, `person_k.min`, `person_k.persons`, `person_k.below_k_share`; utility/composite overall scores are deliberately not privacy components |
| `src/pets_release/run/purpose.py`, `policy/health_s1.py`, `policy/cs_s1.py` | Normal utility threshold 0.90; enumerated sacrifice floors 0.60 (H-U4/H-U6/H-U8), 0.80 (CS-U5); k=5, suppression cap 0.10; CS label recall 0.98 and timestamp floor `ts.hour` |

<!-- IF #24 -->Pending producer source inspected read-only on `ticket/23-cs-s1`
at `fbd72a0bbf4bc4908ea471d81afc51c8cc97521f`:
`src/pets_release/cs_s1/measure.py`, `_target_risks`, writes
`residualRisks[risk=target-recall-national-id]`, `target-recall-payment-card`,
`target-recall-iban`, `target-recall-secret` and `target-precision-secret`.
These use the existing schema's `rate` and `description`, not a new `targetNotes`
object. Recheck that producer on the final SHA before resolving any CS claim.<!-- END IF -->

No absent/null/errored/`not_measured` measurement becomes a number, `false`, or a
pass. Render **“not measured”** and its reason. Distinguish `not_applicable` with
the actual reason; do not count it as a passed target. A table verdict below says
“not measured (prep)” until final proof is available; this does not assert the
current product never measures the field. Compare only after `status=measured`
(utility tasks also require `status=ok`).

## 1. Data types and privacy risks

Show detector column roles and evidence through the detector seam when actually
demonstrated. The release's `inventory` may be policy-derived; do not call it a
detector accuracy result. Use schema names and aggregate metrics only.

| HEALTH-S1 baseline / before | Measured value | Prep verdict |
|---|---|---|
| Scorecard privacy | {{manifest.measured.privacy.components[component=privacy].before}} | not measured (prep) |
| Scorecard share of ROWS below k=5 | {{manifest.measured.privacy.components[component=k_below_5_share].before}} | not measured (prep) |
| Scorecard linkage component (not the two attacker personas) | {{manifest.measured.privacy.components[component=linkage_reid].before}} | not measured (prep) |
| Full k distribution / histogram | not measured: no histogram field in this manifest | not measured |
| Both attacker-persona linkage and attribute inference before protection | not measured: no bound before/after persona pair supplied | not measured |

## 2. PETs and why

For each presented field read `pets`, `fieldJustifications` and `contract` together.
The ladder floor is the most detailed permitted rung; the actual `rung` is what
was released. Tie `reason` to the purpose check. No old band widths, timestamp
detail or column counts are carried forward. Search is bounded; it does not prove
global optimality or excuse utility failures without an enumerated sacrifice.

<!-- IF #106 -->D33: show the exact `lab_results.test_name` rung and H-U7 effect.
If the adopted rung is the CRP-versus-other distinction, say so as a schema-level
choice. If the release instead uses a justified non-QI exception, show its threat
model and residual risk. Do not silently describe either as a full-detail k pass.<!-- END IF -->

## 3. Protected output

Field-level before-to-after, never raw input rows: full birth date → chosen age
band; raw join key → keyed pseudonym; unneeded field → withheld. Present all shown
fields' actual final justifications. Keep protected table schemas visible even
without the optional web app.

<!-- IF #117 -->D41's web row view is human-only for real-kit material. Show the
first approximately ten protected rows per table only after display-time limited
verify and matching manifest-file digests; only manifest-listed files. No raw
input, row maps or truth/. Mandatory label: “Synthetic kit data © Since AI ry,
CC BY 4.0. In a real deployment only the recipient sees this view.” Agents never
read or screenshot this real-kit view. Agent tests/screenshots use hand-made
synthetic fixtures.<!-- END IF -->

## 4. Measured privacy and utility: targets met / not met

### HEALTH-S1 privacy floors

| Privacy target / floor | Measured value from HEALTH-S1 | Targets met / not met |
|---|---|---|
| Person-k ≥ 5 over every released QI including joins | {{manifest.measured.privacy.components[component=person_k.min].after}} | not measured (prep) |
| Share of retained PERSONS below k=5 = 0 | {{manifest.measured.privacy.components[component=person_k.below_k_share].after}} | not measured (prep) |
| Last-step local suppression share ≤ 0.10 | {{manifest.pets[pet=local_suppression,table=ed_visits,column=patient_hetu].params.share}} | not measured (prep) |
| PERSON text recall ≥ 0.95 | not measured; {{manifest.residualRisks[risk=free-text-recall].rate.status}} | not applicable only if final release withholds all free text; never assumed met |
| PHONE text recall ≥ 0.95 | not measured; {{manifest.residualRisks[risk=free-text-recall].rate.status}} | same applicability rule, never assumed met |
| ADDRESS text recall ≥ 0.95 | not measured; {{manifest.residualRisks[risk=free-text-recall].rate.status}} | same applicability rule, never assumed met |
| NATIONAL_ID text recall ≥ 0.95 | not measured; {{manifest.residualRisks[risk=free-text-recall].rate.status}} | same applicability rule, never assumed met |

Report number of persons alongside k:
{{manifest.measured.privacy.components[component=person_k.persons].after}}.
The scorecard's after ROW share is
{{manifest.measured.privacy.components[component=k_below_5_share].after}}; it is
not a PERSON share. Its privacy score
{{manifest.measured.privacy.components[component=privacy].after}} is not a proof
of zero risk: renamed `age_band` is a disclosed scorecard blind spot (D22).

### Required zero-hit checks / export assertions (each demonstrated scenario)

For HEALTH-S1 use its manifest. For CS-S1 these rows are eligible only inside the
#24 claim gate. Each cell is hits/scanned denominator, **not a recall fraction**.
Confirm `exportAssertions.<name>` is literal false AND that its own required
`assertionEvidence` check ran with status pass, correct scope, zero hits and a
positive denominator. Missing evidence is invalid, not “absence proven”.

| Named assertion: zero-hit floor | Measured hits / denominator | Targets met / not met |
|---|---|---|
| nationalIds | {{manifest.assertionEvidence.nationalIds.hits}} / {{manifest.assertionEvidence.nationalIds.denominator.n}} cells | not measured (prep) |
| paymentCards | {{manifest.assertionEvidence.paymentCards.hits}} / {{manifest.assertionEvidence.paymentCards.denominator.n}} cells | not measured (prep) |
| ibans | {{manifest.assertionEvidence.ibans.hits}} / {{manifest.assertionEvidence.ibans.denominator.n}} cells | not measured (prep) |
| accountNumbers | {{manifest.assertionEvidence.accountNumbers.hits}} / {{manifest.assertionEvidence.accountNumbers.denominator.n}} cells | not measured (prep) |
| emails | {{manifest.assertionEvidence.emails.hits}} / {{manifest.assertionEvidence.emails.denominator.n}} cells | not measured (prep) |
| phones | {{manifest.assertionEvidence.phones.hits}} / {{manifest.assertionEvidence.phones.denominator.n}} cells | not measured (prep) |
| ipAddresses | {{manifest.assertionEvidence.ipAddresses.hits}} / {{manifest.assertionEvidence.ipAddresses.denominator.n}} cells | not measured (prep) |
| deviceIds | {{manifest.assertionEvidence.deviceIds.hits}} / {{manifest.assertionEvidence.deviceIds.denominator.n}} cells | not measured (prep) |
| usernames | {{manifest.assertionEvidence.usernames.hits}} / {{manifest.assertionEvidence.usernames.denominator.n}} cells | not measured (prep) |
| propertyIds | {{manifest.assertionEvidence.propertyIds.hits}} / {{manifest.assertionEvidence.propertyIds.denominator.n}} cells | not measured (prep) |
| plates | {{manifest.assertionEvidence.plates.hits}} / {{manifest.assertionEvidence.plates.denominator.n}} cells | not measured (prep) |
| secrets | {{manifest.assertionEvidence.secrets.hits}} / {{manifest.assertionEvidence.secrets.denominator.n}} cells | not measured (prep) |
| urlsWithTokens | {{manifest.assertionEvidence.urlsWithTokens.hits}} / {{manifest.assertionEvidence.urlsWithTokens.denominator.n}} cells | not measured (prep) |
| rawTimestamps | {{manifest.assertionEvidence.rawTimestamps.hits}} / {{manifest.assertionEvidence.rawTimestamps.denominator.n}} cells | not measured (prep) |
| reversibleHashes | {{manifest.assertionEvidence.reversibleHashes.hits}} / {{manifest.assertionEvidence.reversibleHashes.denominator.n}} cells | not measured (prep) |
| keyMaterial | {{manifest.assertionEvidence.keyMaterial.hits}} / {{manifest.assertionEvidence.keyMaterial.denominator.n}} cells | not measured (prep) |
| rowMaps | {{manifest.assertionEvidence.rowMaps.hits}} / {{manifest.assertionEvidence.rowMaps.denominator.n}} files | not measured (prep) |
| quasiIdentifiersBelowK (HEALTH-S1 only) | {{manifest.assertionEvidence.quasiIdentifiersBelowK.hits}} / {{manifest.assertionEvidence.quasiIdentifiersBelowK.denominator.n}} persons | not measured (prep) |

### HEALTH-S1 purpose-check thresholds

The original threshold remains 0.90. An enumerated sacrifice can permit a lower
score at its fixed floor; label it **accepted sacrifice**, not original target met.
A score below either applicable floor, a null, or an errored task fails. Show both
before and after the actual last-step suppression, not a pre-suppression candidate.

| Purpose check | Original threshold | Enumerated sacrifice floor | Before | After | Targets met / not met |
|---|---|---|---|---|---|
| H-U2 | ≥ 0.90 | none | {{manifest.measured.utility.tasks[task=H-U2].before}} | {{manifest.measured.utility.tasks[task=H-U2].after}} | not measured (prep) |
| H-U4 | ≥ 0.90 | {{manifest.sacrifices[check=H-U4].floor}} (policy 0.60) | {{manifest.measured.utility.tasks[task=H-U4].before}} | {{manifest.measured.utility.tasks[task=H-U4].after}} | not measured (prep) |
| H-U6 | ≥ 0.90 | {{manifest.sacrifices[check=H-U6].floor}} (policy 0.60) | {{manifest.measured.utility.tasks[task=H-U6].before}} | {{manifest.measured.utility.tasks[task=H-U6].after}} | not measured (prep) |
| H-U7 | ≥ 0.90 | none | {{manifest.measured.utility.tasks[task=H-U7].before}} | {{manifest.measured.utility.tasks[task=H-U7].after}} | not measured (prep) |
| H-U8 | ≥ 0.90 | {{manifest.sacrifices[check=H-U8].floor}} (policy 0.60) | {{manifest.measured.utility.tasks[task=H-U8].before}} | {{manifest.measured.utility.tasks[task=H-U8].after}} | not measured (prep) |

Overall pets-eval utility and composite before/after: **not measured in the current
manifest**. The current measurer writes task scores and privacy components, not
these summary fields. Do not invent `measured.privacy.components[component=utility]`
or use `measured.baselines` as this release's result. If a final producer adds
summary keys, document the real keys and bind them before quoting their numbers.

<!-- IF #24 -->
### CS-S1 privacy floors and purpose-check thresholds

| Privacy target / floor | Measured value from CS-S1 | Targets met / not met |
|---|---|---|
| NATIONAL_ID exact-match recall ≥ 0.98 | {{manifest.residualRisks[risk=target-recall-national-id].rate.value}}; {{manifest.residualRisks[risk=target-recall-national-id].description}} | not measured (prep) |
| PAYMENT_CARD exact-match recall ≥ 0.98 | {{manifest.residualRisks[risk=target-recall-payment-card].rate.value}}; {{manifest.residualRisks[risk=target-recall-payment-card].description}} | not measured (prep) |
| IBAN exact-match recall ≥ 0.98 | {{manifest.residualRisks[risk=target-recall-iban].rate.value}}; {{manifest.residualRisks[risk=target-recall-iban].description}} | not measured (prep) |
| SECRET exact-match recall ≥ 0.98 | {{manifest.residualRisks[risk=target-recall-secret].description}} | **not met (D45)**; later figure optimistic, not untouched holdout proof |
| No HEALTH in released text; healthInText hits = 0 | {{manifest.assertionEvidence.healthInText.hits}} / {{manifest.assertionEvidence.healthInText.denominator.n}} turns | not measured (prep); bounded by the independent check's coverage |
| conversations.started_ts at hour or coarser | {{manifest.fieldJustifications[table=conversations,column=started_ts].rung}} | not measured (prep); confirm contract form and fresh gate |
| turns.ts at hour or coarser | {{manifest.fieldJustifications[table=turns,column=ts].rung}} | not measured (prep); confirm contract form and fresh gate |

| Purpose check | Original threshold | Enumerated sacrifice floor | Before | After | Targets met / not met |
|---|---|---|---|---|---|
| CS-U1 | ≥ 0.90 | none | {{manifest.measured.utility.tasks[task=CS-U1].before}} | {{manifest.measured.utility.tasks[task=CS-U1].after}} | not measured (prep) |
| CS-U3 | ≥ 0.90 | none | {{manifest.measured.utility.tasks[task=CS-U3].before}} | {{manifest.measured.utility.tasks[task=CS-U3].after}} | not measured (prep) |
| CS-U4 | ≥ 0.90 | none | {{manifest.measured.utility.tasks[task=CS-U4].before}} | {{manifest.measured.utility.tasks[task=CS-U4].after}} | not measured (prep) |
| CS-U5 | ≥ 0.90 | {{manifest.sacrifices[check=CS-U5].floor}} (policy 0.80) | {{manifest.measured.utility.tasks[task=CS-U5].before}} | {{manifest.measured.utility.tasks[task=CS-U5].after}} | not measured (prep) |

**D45, do not shorten away the shortfall:**
{{manifest.residualRisks[risk=target-recall-secret].description}}

That complete manifest target note is the source for the historical **15/17 before
the redactor change** (about 0.88) against **0.98**, the later count/denominator and
the contamination warning. Keep the count and denominator inside this placeholder,
not hand-typed into submitted text. The existing schema has no separate historical
`tp`/`support` fields: do not invent them. Current `measured.redaction.labels` counts
cannot replace the pre-change count. The note's `rate.denominator.n` is held-out
**turns**, not SECRET spans; never use it as the SECRET recall denominator.

The later result is **optimistic** because held-out misses informed the rule.
The target is not lowered or described as met on untouched data. State exact match,
evaluation frame and the accepted turn-level template-held-out split. Gate zero
hits protects only within the independent check's coverage; it is not recall proof.
If this target note is absent, keep “not measured” for its values and block final
CS-S1 claim approval until the manifest carries D45; do not silently omit D45.

D29 fallback: only claim strict/no-withholding or fallback after reading the final
manifest and proof. If turns were withheld, quote the real sacrifice note/count,
CS-U1/CS-U5 effects and reduced checker independence. No invented fallback count key.
<!-- END IF -->

## 5. Sharing scenario and limitations, then proof

For each release show recipient, purpose and trust level; `fitFor`, `notFitFor`,
`sacrifices`, `residualRisks`. Pseudonymised data is still personal data; the
controller retains the key. Synthetic templated data does not establish general
speech performance. Recipient digests catch accidental changes, not a determined
editor; only full verify checks the HMAC signature.

Attacker linkage after protection:
{{manifest.residualRisks[risk=linkage-attackers].rate.status}}; attribute inference:
{{manifest.residualRisks[risk=attribute-inference].rate.status}}. If either status
is `not_measured`, write “not measured”, never zero. To claim both personas, require
actual per-persona measured risk entries bound to the final inputs and document
their IDs; a generic note or scorecard linkage number is insufficient.

Gate status: {{manifest.gate.status}}. Read actual `gate.checks` entries; derive
pass N / required applicable N and separately count declared not-applicable checks.
Never count a missing/error/not-run result as a pass or invent `.count` JSON keys.
Run the real CLI for limited verify and full verify on that same release and SHA;
record the actual outputs, exits and check totals in SOURCES. No verify outcome
field exists in the manifest. Demonstrate a refusal on hand-made synthetic input
with the real CLI and report check/count only. These are pending proof actions,
not claims that this prep ran the release, gate or verify successfully.

## Claim gates and finalisation handoff

Only retain text inside `<!-- IF #n -->...<!-- END IF -->` when issue #n's work is
merged **and** the particular claim is verified on the final SHA. Otherwise drop
the whole block; remove the markers in either outcome. A closed issue alone is
not merge or measurement evidence. Markers are drafting instructions, not claims.

| Enabling issue | Finalisation condition |
|---|---|
| #24 | CS-S1 producer + privacy must-fixes merged; real final-SHA release, both verify tiers, per-label notes, D45 and any D29 sacrifice disclosed |
| #32 | D39 go decision after both releases pass; front end merged and verified; no-go/unmerged becomes future work only |
| #117 | Web app merged; final-SHA evidence for display-time verification, manifest-listed file/digest binding and D41 label; real-kit row view never read by agents |
| #127 | Parallel search merged; final-SHA determinism across worker counts, offline workers and fail-closed worker error; no timed speed claim without measurement |
| #106 | D33 rung or disclosed threat-model exception actually merged and present in final release; H-U7 effect measured |

Finaliser creates `docs/story/final/` only after review + fresh proof. Required:
`name.txt` (≤80 characters), `tagline.txt` (≤140), `description.md` (≤5,000; no
headings/editorial notes), `built-with.txt` (first five chips in 01),
`pitch-4min.md`, `video-script.md`, `SOURCES.md`.

SOURCES is a plain Markdown note, **no HTML comments**. Record exact final SHA,
absolute HEALTH-S1 and eligible CS-S1 manifest paths, input digests, each retained
claim/number's scenario + actual key/selector, and real gate/verify/refusal commands
and exits. Fixed policy thresholds and presentation timings cite their spec/code,
not a fabricated measurement. Resolve all placeholders; keep “not measured” with
reason where unavailable. Have independent Spec review check claims against those
exact manifests and Standards review check vocabulary and content freedom.

Readiness CLI: `python docs/story/check_final.py` (defaults to this checkout's
`docs/story/final/`; explicit folder argument is for synthetic fixtures). It fails
on missing/empty deliverables, unresolved placeholders, comment/claim markers,
common editorial notes, description headings and over-limit text. It does not
certify claim truth, proof freshness or absence of all possible editorial wording.
Count actual final text including whitespace/newlines, not just visible prose.

`tests/story_kit/test_final_story.py` exercises that CLI on planted
`docs/story/final/` fixtures. The real-folder readiness test has the named skip
`story-finalisation-awaits-final-review-and-final-sha-proof` only while the folder
is absent. That skip is **not a pass** and blocks closing #103; once any real
final folder exists, missing files/markers/limits fail normally. No final content
or release evidence is minted by this preparation.
