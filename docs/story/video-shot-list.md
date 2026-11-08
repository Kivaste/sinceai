# Demo video shot list — HEALTH-S1

**FINAL at c52424c (merged to main cc66ac2)**.
The final-release measurements below are NOT the recorded video on demo pin
`5b260ec`. Keep that recording and its build label unchanged (D55); never copy
these measurements onto old captures. A new capture needs its own matching proof.

For the business teammate, side lane D48. **Runtime: 110 seconds; seven shots.**
The optional LLM shot replaces its default shot; it never adds time. Start in the
working local app, not on a title slide. The organiser items appear in order:
data types and risks → PETs and reasons → protected output → measurements →
scenario and limitations. The proof beat supports the measurements.

This is recording guidance, not evidence of a successful capture. Final
measurements come from the pinned HEALTH-S1 manifest using the rules in
`06-numbers-to-fill.md`. Timings, shot/item labels, issue IDs and the mandatory
licence label are production instructions, not measured claims. No invented
counts, thresholds, speeds or scores. Missing measurements say **not measured**.
The pin and release must match the actual recorded proof. The description/deck
now use final numbers; the existing video remains labelled with its
own demo build, never relabelled as final proof.

## Timing table

| Shot | Start–end seconds | On screen: app view or terminal command | Voice-over (plain, short sentences) | Organiser item |
|---|---|---|---|---|
| 1 | 0–12 | Local app, completed HEALTH-S1 run → field inventory. Click to expand column roles and schema-level evidence immediately. Show direct identifiers, quasi-identifiers, sensitive attributes and free text, never source rows. Do not call a policy-derived inventory a detector accuracy result. | “Names are not the only privacy risk. Ages, places, times and linked records can identify people. The tool shows each field's role.” | 1 — data types and privacy risks |
| 2 | 12–22 | **Default:** purpose checks / needs spec, expanding a field's reason. **Optional Mistral LLM, 10 seconds:** enter a schema-only request, “Study emergency-visit crowding and revisits”, and show the actual validated policy draft for human review, not a mock. Include only when the real path works on the recording's pin. This replaces the default shot; it does not show draft-to-search integration. | **Default:** “We start with the purpose. Each field must justify why it is needed.” **Optional:** “Describe the request in plain language. The front end drafts a policy for human review. It receives no row values.” | 2 — purpose-first selection |
| 3 | 22–40 | App → field justifications and PETs. Step through `patient_name` / `clinical_notes` → withheld; `visit_id` → keyed pseudonym for necessary joins; `date_of_birth` → `age_band` for analysis. Read actual chosen rungs, purpose-check reasons and any local suppression from the pinned release, not an old plan. Show field/value-form changes only; no raw examples or numeric band boundaries. | “Names and clinical notes are not needed, so they are withheld. Keyed pseudonyms keep necessary joins. Age bands replace birth dates. Each choice has a purpose-check reason.” | 2 — methods and why, field by field |
| 4 | 40–56 | App → **protected rows view**, after protection only. The human recorder opens it only after display-time limited verification and manifest-file digest checks pass. Keep this entire label legible: **“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient sees this view.”** Never show raw input, row maps or `truth/`. | “These are the protected tables the recipient receives. This is synthetic challenge data. In a real deployment, only the recipient sees this view.” | 3 — protected output |
| 5 | 56–78 | App → before/after scorecard, then **targets met / not met** table. Final privacy `0.1716` → `1.0`; utility mean `1.0` → `0.9188`; linkage `0.5697` → `0`; below-k=5 ROW share `0.9557` → `0`. H-U2 `0.9195`: accepted 30-minute-bin detail sacrifice, still above `0.90`; H-U4 `0.7952`: below `0.90`, accepted at `0.6`. H-U6/H-U7/H-U8 `0.9462`/`0.9827`/`0.9504`. Show person-k minimum `5`, below-k share `0`, over `24,204` persons on both QI sets. No blanket k hiding. These numbers belong only on a matching final-release capture, not the old video. | “The five-task utility mean is 0.9188. Person-k meets five on the declared QIs. H-U4 misses its original target but meets the accepted sacrifice floor. These are measured trade-offs, not perfect privacy.” | 4 — measured privacy and utility |
| 6 | 78–92 | Brief app gate summary. Final gate: **42 checks, 42 pass, 0 not applicable, 0 non-passing**. Show matching actual terminal results: `pets-release verify $R`, followed by `$LASTEXITCODE`; `pets-release verify --full --kit $K $R`, followed by `$LASTEXITCODE`. Final release and both verify exits are `0` (PRE-FILL-SOURCES). Do not substitute these for an older pin's proof. Frame content-free summaries; exclude row values, secrets and tokens, not aggregate k figures. | “The gate passes 42 named checks. Both verification tiers exit zero. Recipient verification is limited; full verification needs the controller's inputs and key.” | 4 — proof supporting the measurements |
| 7 | 92–110 | App → recipient, controlled-research trust, `fitFor` / `notFitFor`, sacrifices and residual risks. Keep the renamed-age_band scorecard blind spot and exact test_code test-history risk visible. Caption: red-team unique re-identifications `0` within tested frames; population diagnosis lift `2.1351x`, no enforced bound; los_minutes lift `1.6894x`, bound `2.0x`; with diagnosis known, `73.6%` of persons below k=5. Population lifts are not sampled attacker rates. test_name is withheld; never relabel earlier captures. | “This serves controlled research, not individual care. Zero unique red-team matches is not anonymity. Diagnosis inference remains, and knowing diagnosis puts 73.6 percent below k five. Those residual risks stay disclosed.” | 5 — scenario and honest limitations |

**Recording guardrails:** HEALTH-S1 only. CS-S1 is dropped under D46; its strict-gate
refusal is a Q&A answer, not a shot. No hosted URL, Docker screen or cloud demo.
k figures may now be shown with their QI scope and person/row denominators. The
final manifest records `lab_results.test_name` as withheld, consistent with 06;
do not describe it as retained outside k or relabel earlier
demo-pin captures. A gate pass proves its named checks, not anonymity.
Limited verification does not authenticate the controller's signature. Full
verification checks it with the key. The scorecard's renamed-age-band blind spot
is not evidence of absent risk. Mean utility is derived from five task scores,
not an invented manifest summary field; no overall composite is supplied. The
evidence-pack exporter exists (#147), and Mistral drafts policies for human review;
neither is a fresh integration run in the measured proof. Legal basis/DPIA remain
controller-supplied. A fresh planted-violation refusal is not recorded there.

## Before you record

- [ ] Use the agreed pinned integration revision and its matching HEALTH-S1 release
  and matching proof. Use the final measurements in 06 for a final-release capture;
  no old gate totals or recycled success lines. Do not stage a successful outcome.
- [ ] Start the local server on this machine with the demo click-through wizard
  (D48), which sets the HMAC key in the server's environment only and passes the
  kit, output and creation-time arguments the app requires. Use the exact launch
  command in the README's web-app section; `python -m pets_release.ui` alone exits
  2 without the required configuration. Open the
  loopback token link it prints. Keep the token and key off camera; no hosted URL.
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
- [ ] Show final k with its scope: both QI sets, 24,204 persons, minimum 5 and
  below-k share 0; distinguish the 73.6% diagnosis-known residual risk. Do not
  conceal unmet targets or label final k as pending.
- [ ] Include the optional Mistral shot only if its real
  request-to-draft path works there. Otherwise use the default shot. Only request
  text and field names may reach the LLM, never row values.
- [ ] Prepare the same release's static dashboard with
  `pets-release dashboard $R --out $Dashboard`, where `$Dashboard` is a local HTML
  path set off camera. Rehearse its content-free crop and scoped k presentation.
- [ ] **Close other windows**, notifications, file previews and unrelated tabs.
  Hide the address bar, token, terminal history and private paths. Keep only the
  app and the proof terminal ready; no source CSV, row map or truth view.

## If something goes wrong

1. Switch to the same pinned release's static dashboard HTML: “This is the saved dashboard from this release, not a live app run.”
2. Follow its field, PET, scorecard, targets and limitations sections; show final k with its scope and diagnosis-known caveat; use only actual matching proof outputs.
3. Do not fake the rows view or a pass: say “The protected rows view is unavailable”; this fallback is a rehearsal aid, not a complete submission video—re-record the required labelled app view when restored.
