# Four-minute pitch and six-minute Q&A draft

**PRE-FILL at df79ec20538e8f02b3256911fb01d549e5af0ebb** (#103, D61).
Five beats follow D40, not feature count. Numbers trace to this build's manifest
through `PRE-FILL-SOURCES.md`; refresh from the final manifest after the freeze.
This is not final-SHA proof or submission readiness.

“sinceai's product is the engine: a library and CLI running as a self-hosted
pipeline step in your infrastructure, from CI, Airflow or dbt. The web app is the
approval and audit console for one run. A self-hosted REST API is future work.”

## 1. Data types and privacy risks (0:00–0:40)

“A hospital needs to share emergency-visit data with a university research group
studying crowding and revisits. Removing names leaves ages, places, timestamps and
joins. Our field inventory records the column roles and their evidence.”

Show the detector separately from the release inventory: a policy-derived inventory
is not evidence that the detector measured those roles. Supporting scorecard privacy:
0.1716. Below-k ROW
share before protection:
0.9557179814438992. Attacker
persona rates: not measured (#138 at this revision). A full k histogram is not
measured (no histogram field). A scorecard linkage component is not both attacker
personas; linkage zero means no shared QIs left to match on, not resistance.

## 2. PETs and why (0:40–1:20)

“The data request becomes purpose checks. Withholding avoids sharing unneeded
fields. Keyed pseudonyms preserve required joins; generalisation and local
suppression reduce quasi-identifier detail. Each field justification names the
chosen rung, ladder floor and reason.”

Show `pets`, `fieldJustifications` and purpose checks together. Read actual rungs
and parameters, not an old hand plan. A bounded detail-ladder search is not proof
of a global optimum or that every original utility threshold was met.

Search optimises k and purpose-check utility, not attackers. Attacker measurements
are post-hoc. No parallel-search speed-up is measured by this run.

## 3. Protected output (1:20–1:55)

Show field-level before-to-after changes from `fieldJustifications`: birth date
to `age_band`, names and `clinical_notes` withheld, required join keys pseudonymised.
Show `lab_results.test_name`'s actual rung and its H-U7 score from 06. Reporting
that rung is not proof of D58's all-kept-catalogued-QI coverage: not measured (#146).

The human can show protected real-kit rows only through the web
app's display-time limited verify and matching manifest-file digests. Label:
“Synthetic kit data © Since AI ry, CC BY 4.0. In a real deployment only the recipient
sees this view.” No raw input, row maps or truth/. Agents never inspect or
screenshot the real-kit row view; synthetic fixtures only.

## 4. Measured privacy and utility (1:55–3:10)

Display the full targets met / not met table from 06. Show original thresholds
beside policy sacrifice floors, and post-suppression purpose-check scores.
Producer-attested per-person minimum k on this manifest's QI set:
5.0; PERSON
share below k:
0.0.
Scorecard privacy after:
1.0. Disclose its
renamed-`age_band` blind spot. Overall scorecard utility and composite: not measured
in this manifest; never substitute baseline utility or composite scores. Per-person
k needs the key holder's full verification; recipients cannot independently
recompute it. Separate k on both D58 QI sets: not measured (#146). k with diagnosis
known and its measured risk share: not measured (#143); never estimate the share.

“CS-S1 is future work, dropped from the demoable cut under D46. Its strict-gate
refusal is a limitation, not a released scenario. The CS evaluation path uses
typed, numbered placeholders and D37 masking, never realistic fake values. Typed
labels are clearer and avoid accidental matches in the shared synthetic population.”
CS-S1 recall and purpose-check figures: not measured (no CS manifest in this run).

## 5. Sharing scenario and limitations, then proof (3:10–4:00)

“The release serves these purpose checks for this recipient and trust level, not
individual care or arbitrary reuse. Pseudonymised data is still personal data.
The data is synthetic and templated. Unmeasured risks are not zero.”

Show the manifest's `fitFor`, `notFitFor`, `sacrifices`, `residualRisks`; then this
build's actual gate N/N (not-applicable separately), limited verify and full verify
outcomes from PRE-FILL-SOURCES. Final-SHA refusal: not demonstrated by this run.
Before final submission, show a deliberate synthetic refusal
through the real CLI, with check name and counts only. Never reuse an old green
line. Limited verify cannot authenticate the HMAC signature; full verify needs the
controller's inputs and key. “Share only what the purpose needs.”

“The pipeline publishes only after a release and successful verification. Exit 1
means refused or failed check; exit 2 means bad input/configuration or unknown state.
Both stop publication. Rows and keys stay in-house; optional LLM drafting receives
only request/schema information and is not an integration demonstrated by this run.”

D60 evidence pack: not generated (#147 pending at this build). It is a DPO/Findata-
shaped document from the authenticated signed manifest: purpose, method/parameters,
measured attacker risk, utility, residual risks and reproducibility. Legal basis
and DPIA are “to be supplied by the controller”, not legal approval from a score.

## Jury Q&A

| Question | Honest answer |
|---|---|
| Does a passed gate mean anonymity? | No. Assertions cover named checks and labels only; residual risks remain. Pseudonymised data is personal data. |
| Which targets did you miss? | Read 06's final table. An accepted policy sacrifice is not a full pass at the original utility threshold; unavailable values say not measured. |
| Can the recipient verify everything? | No. Limited verify re-runs release-scope checks; person-k is producer-attested. Producer-scope checks and signature need full verify with inputs and key. |
| Does the scorecard prove attack resistance? | No. Its renamed-age-band blind spot is disclosed; person-k and row-k are distinct. Both attacker-persona rates must be measured separately or say not measured. |
| What if the gate misses a name? | Low-severity text labels have residual risks, not universal absence assertions. Known coverage gaps and the evaluation frame stay visible. |
| Is the processing offline? | The release engine blocks network access; do not confuse an optional request-only front end with transmitting rows. Same inputs, key, creation time and versions must produce identical bytes; demonstrate rather than assert a new run passed. |
| What remains future work? | Unmerged or unverified optional features, broader sharing scenarios and generalisation beyond templated synthetic data. |
| How does it fit our platform? | Run the library/CLI inside CI, Airflow or dbt today. The web app is the approval and audit console; self-hosted REST API is future work. |
| What happens when privacy checks fail? | Exit 0 releases; publish only after successful verification. Exit 1 refuses or fails; exit 2 is bad input/configuration or unknown. Either nonzero exit stops publication. |
| Does our data leave our infrastructure? | Source rows and keys stay local; only approved protected tables and the content-free signed manifest go to the intended recipient. The optional LLM front end drafts a validated purpose-first policy from request and schema information only (never row values) for human review; feeding the draft into the search is future work. |
| Why no realistic fake names? | Typed, numbered placeholders make redaction explicit and avoid accidental matches with the shared population. This CS evaluation choice is not a passed CS-S1 release claim. |
| Where is the CS-S1 release? | Future work under D46; the strict-gate refusal is an honest limitation. No CS-S1 measurements are claimed from the HEALTH-S1 manifest. |
| Does the evidence pack replace a DPIA? | No. #147 is not generated in this PRE-FILL; legal basis and DPIA remain controller-supplied, even when an evidence pack is available. |
| Did unseen detection achieve a perfect score? | No accuracy score is claimed. The export requires full column coverage, with privacy_role and subtype for every column; omission refuses the export. The organisers score both dimensions. |
