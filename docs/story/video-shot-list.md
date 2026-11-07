# Demo video shot list — HEALTH-S1

For the business teammate, side lane D48. **Runtime: 110 seconds; seven shots.**
The optional LLM shot replaces its default shot; it never adds time. Start in the
working local app, not on a title slide. The organiser items appear in order:
data types and risks → PETs and reasons → protected output → measurements →
scenario and limitations. The proof beat supports the measurements.

This is recording guidance, not evidence of a successful run. #103 fills every
measurement from the final HEALTH-S1 manifest using the source rules in
`06-numbers-to-fill.md`. Timings, shot/item labels, issue IDs and the mandatory
licence label are production instructions, not measured claims. No invented
counts, thresholds, speeds or scores. Missing measurements say **not measured**.
The pin and release must match the actual recorded proof; if finalisation changes
the revision or release, refresh the affected captures rather than relabel old proof.

## Timing table

| Shot | Start–end seconds | On screen: app view or terminal command | Voice-over (plain, short sentences) | Organiser item |
|---|---|---|---|---|
| 1 | 0–12 | Local app, completed HEALTH-S1 run → field inventory. Click to expand column roles and schema-level evidence immediately. Show direct identifiers, quasi-identifiers, sensitive attributes and free text, never source rows. Do not call a policy-derived inventory a detector accuracy result. | “Names are not the only privacy risk. Ages, places, times and linked records can identify people. The tool shows each field's role.” | 1 — data types and privacy risks |
| 2 | 12–22 | **Default:** purpose checks / needs spec, expanding a field's reason. **Optional LLM, 10 seconds — include only if #32 merged before the pin:** enter a schema-only request, “Study emergency-visit crowding and revisits”, and show the returned drafted purpose-first policy. Show an actual response, not a mock. This replaces the default shot. | **Default:** “We start with the purpose. Each field must justify why it is needed.” **Optional:** “Describe the request in plain language. The front end drafts a purpose-first policy. It receives no row values.” | 2 — purpose-first selection |
| 3 | 22–40 | App → field justifications and PETs. Step through `patient_name` / `clinical_notes` → withheld; `visit_id` → keyed pseudonym for necessary joins; `date_of_birth` → `age_band` for analysis. Read actual chosen rungs, purpose-check reasons and any local suppression from the pinned release, not an old plan. Show field/value-form changes only; no raw examples or numeric band boundaries. | “Names and clinical notes are not needed, so they are withheld. Keyed pseudonyms keep necessary joins. Age bands replace birth dates. Each choice has a purpose-check reason.” | 2 — methods and why, field by field |
| 4 | 40–56 | App → **protected rows view**, after protection only. The human recorder opens it only after display-time limited verification and manifest-file digest checks pass. Keep this entire label legible: **“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view.”** Never show raw input, row maps or `truth/`. | “These are the protected tables the recipient receives. This is synthetic challenge data. In a real deployment, only the recipient sees this view.” | 3 — protected output |
| 5 | 56–78 | App → before/after scorecard, then **targets met / not met** table. Privacy: `{{manifest.measured.privacy.components[component=privacy].before}}` → `{{manifest.measured.privacy.components[component=privacy].after}}`. Purpose-check utility: `{{manifest.measured.utility.tasks[task=H-U2].before}}` → `{{manifest.measured.utility.tasks[task=H-U2].after}}`; show H-U4's `{{manifest.measured.utility.tasks[task=H-U4].before}}` → `{{manifest.measured.utility.tasks[task=H-U4].after}}` beside sacrifice floor `{{manifest.sacrifices[check=H-U4].floor}}`. Keep original target, measured result and verdict distinct; #103 sources thresholds under the existing source contract, never guesses a manifest key. Show accepted sacrifices, unmet targets and not measured entries honestly. **Hide every k figure**, including thresholds, row shares, chart axes and tooltips. If the table includes a k row, mask its numeric cells and mark it **“pending D33”**, not met. | “Here are privacy and utility before and after protection. The table shows which targets are met and which are not. An accepted sacrifice is not a full pass. Missing measurements stay unmeasured.” | 4 — measured privacy and utility |
| 6 | 78–92 | Brief app gate summary: **passing N of N applicable required checks**, with both totals derived by #103 from `{{manifest.gate.checks}}`, not invented count keys; distinguish not-applicable checks. Then terminal results from the same pinned release: `pets-release verify $R`, followed immediately by `$LASTEXITCODE`; `pets-release verify --full --kit $K $R`, followed immediately by `$LASTEXITCODE`. Show actual recipient limited / controller full outcomes and both exit codes. Commands may finish before recording; retain their real command/result pairs. Frame only content-free summaries and exits; exclude k figures, values, secrets and tokens. | “The gate passes its named checks. Recipient verification is limited. Full verification needs the controller's inputs and key. These are the actual exit codes.” | 4 — proof supporting the measurements |
| 7 | 92–110 | App → recipient, controlled-research trust, `fitFor` / `notFitFor`, sacrifices and residual risks. HEALTH-S1 only: hospital → university research group, crowding and revisits. Keep the actual unmet purpose checks and sacrifices visible. Explain that `test_name` remains outside k pending D33 / #106; show no k figure. Keep the scorecard's renamed-`age_band` blind spot and any unmeasured attacker risks explicit. | “This release serves controlled research on crowding and revisits, not individual care or arbitrary reuse. Detail is sacrificed. Pseudonymised data is still personal data. Lab test-name coverage is pending. The scorecard has blind spots. Unmeasured risks remain unknown.” | 5 — scenario and honest limitations |

**Recording guardrails:** HEALTH-S1 only. CS-S1 is dropped under D46; its strict-gate
refusal is a Q&A answer, not a shot. No hosted URL, Docker screen or cloud demo.
Do not quote k in narration or show any k figure, even if later finalisation has
new measurements. Until #106 lands, `test_name` stays outside k; do not imply the
pending D33 work shipped. A gate pass proves its named checks, not anonymity.
Limited verification does not authenticate the controller's signature. Full
verification checks it with the key. The scorecard's renamed-age-band blind spot
is not evidence of absent risk. Overall scorecard utility/composite stay **not
measured** unless the final manifest actually supplies them.

## Before you record

- [ ] Use the agreed pinned integration revision and its matching HEALTH-S1 release
  and fresh proof. #103 resolves manifest placeholders before the final capture;
  no old gate totals or recycled success lines. Do not stage a successful outcome.
- [ ] Start the local server on this machine: `python -m pets_release.ui`. Open
  the loopback token link it prints. Keep the token and key off camera; no hosted URL.
- [ ] Pick **HEALTH-S1**, start the run and **let the run finish** before recording.
  Open the field inventory and rehearse its expansion, so the tool is visibly
  working from the opening shot. Do not spend the video waiting for processing.
- [ ] Confirm the gate and both verify tiers really passed on the same release.
  Set local PowerShell variables `$R` (release folder) and `$K` (kit root) off
  camera; prepare the terminal command/result pairs and their actual exit codes.
  Do not print the key or environment. A missing, errored or failed check blocks
  a passing-proof recording; show the real failure instead of a success claim.
- [ ] Human recorder: open the protected rows view, confirm its display-time
  checks pass, and **check the full D41 label is visible** at recording size.
  Agents must never inspect or screenshot real-kit rows; agent rehearsals use
  hand-made synthetic fixtures only. Do not paste row values into this document.
- [ ] Rehearse crops: no k figures anywhere, including terminal output, scorecards,
  tooltips and target thresholds. Any k target row reads **pending D33** with its
  numeric cells out of frame or masked; do not conceal other unmet targets.
- [ ] Include the optional shot only if #32 merged before the pin and its real
  request-to-draft path works there. Otherwise use the default shot. Only request
  text and field names may reach the LLM, never row values.
- [ ] Prepare the same release's static dashboard with
  `pets-release dashboard $R --out $Dashboard`, where `$Dashboard` is a local HTML
  path set off camera. Rehearse its content-free crop and the no-k framing.
- [ ] **Close other windows**, notifications, file previews and unrelated tabs.
  Hide the address bar, token, terminal history and private paths. Keep only the
  app and the proof terminal ready; no source CSV, row map or truth view.

## If something goes wrong

1. Switch to the same pinned release's static dashboard HTML: “This is the saved dashboard from this release, not a live app run.”
2. Follow its field, PET, scorecard, targets and limitations sections; hide k figures and keep any k target marked “pending D33”; use only actual matching proof outputs.
3. Do not fake the rows view or a pass: say “The protected rows view is unavailable”; this fallback is a rehearsal aid, not a complete submission video—re-record the required labelled app view when restored.
