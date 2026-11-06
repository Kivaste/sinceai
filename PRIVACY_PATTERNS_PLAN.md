# Four privacy patterns: how we win TrustED PETs Transformer

Companion to `HACKATHON_PLAN.md`, which holds the overall solution, timeline and checklist. That plan is a scenario-driven PET compiler (S1) with a free-text redactor (S2) inside it. This file describes four design patterns that run through **both** parts, how each one earns points with the judges, and how to show them in the demo and the Q&A.

Written Fri 6 Nov 2026.

---

## 1. Thesis

> **Protect the data, keep its value, and prove it.**

Most teams will show transformations: names masked, ages binned, text redacted. We show a **release pipeline**:
- it applies the right PET per field and per scenario;
- it **refuses to publish** anything that breaks the scenario's contract;
- it ships a machine-checkable **privacy manifest** that states what was removed, what was kept, and what risk remains, with measured numbers;
- it never sends data anywhere.

The four patterns come from our own product, taskuMentor, a teacher-reflection app that processes classroom lesson recordings. There, transcripts are reduced to closed, content-free observations on an isolated machine. We bring privacy engineering that has already been built and tested, not ideas invented this weekend. That is the one-sentence origin story for the pitch.

| Pattern | One-line description |
|---|---|
| P1: keyed, consistent pseudonyms | The same entity always gets the same pseudonym within its scope, so joins and who-said-what survive. Keys are scoped per conversation, per release or per recipient. |
| P2: closed release contract and fail-closed gate | Every scenario declares exactly what may leave. An independent check refuses the whole release on any violation. |
| P3: privacy manifest | A content-free, machine-checkable record of method, parameters, measured risk before and after, measured utility before and after, and residual risks. |
| P4: fully offline | No network, no cloud model, deterministic output, and temporary state kept only in memory. |

### Our strongest differentiator: proof of what was protected

In the taskuMentor comparison, this was the capability where we are **stronger than most teams will be**. In taskuMentor every privacy flag is typed as a literal `false`, and the validator fails closed.

Most teams will *say* "no identifiers remain". Our manifest does three things instead:
- it **can only say `false`**;
- each `false` is **backed by a named check** that ran on the actual output;
- anyone can **re-run those checks** against the release.

If a check fails, no manifest saying `true` is ever written; the release is refused instead. Details are in section 6, under "Every assertion is proved, not declared". Make this the headline of the Innovation story.

---

## 2. How the patterns map to the judging criteria

Since AI's criteria (no weighted rubric):

| Criterion | What judges look for | How the patterns deliver it |
|---|---|---|
| **Technical implementation**: correct, reliable PET choices | Right PET for each field; nothing breaks | P2 checks every release against the scenario automatically. P1 uses keyed HMAC, which the scorecard's hash-reversal attack cannot reverse. |
| **Innovation**: intelligent, explainable approach | Not just "we masked it" | **Headline:** P3 assertions can only be `false`, each is proved by a named check, and anyone can re-run the checks. P2 refuses releases instead of trusting itself. P1 recipient-scoped keys stop two recipients from joining their copies. |
| **Impact**: less disclosure risk, utility kept | Numbers before and after | P3 records measured risk and utility before and after for every release. P1 keeps joins and dialogue structure, so utility survives. |
| **Presentation**: clear scenario, before/after, honest limitations | A story, evidence, candour | P3 *is* the before/after and the limitations section. P2 gives a live refusal moment. P4 gives a simple trust message. |

The five required demo items map onto P3's sections (section 5.3).

---

## 3. Solution shape

```
original data (dtype=str)
  -> DETECT     column roles + text spans, each with a reason          (HACKATHON_PLAN S1 detect, S2 text)
  -> SELECT     scenario policy -> PET per column / per span label    (HACKATHON_PLAN S1 select)
  -> TRANSFORM  P1 pseudonyms, generalisation, suppression, rounding, redaction, DP
  -> GATE       P2: contract check + independent rescan + leftovers + k where required -> refuse or continue
  -> WRITE      atomic release folder + P3 privacy_manifest.json        (row maps written outside, never published)
  -> MEASURE    pets-eval scorecard (correct scenario ID) + our own exact-match metrics -> into the manifest
  -> SHOW       dashboard rendered from the manifest

Every stage runs under P4: network blocked, deterministic, no data persisted outside the release.
```

**Demo scope.**
- **Text:** `customer_service` **CS-S1**, transcripts going to an external LLM vendor. This is the strongest privacy story, with the largest measured risk: free-text leakage of 0.80 under the baselines.
- **Tabular:** the scenario chosen in `HACKATHON_PLAN.md` §7 (HEALTH-S1 or FIN-S1).
- **Detection:** live detection on `unseen`.

---

## 4. Pattern 1: keyed, consistent pseudonyms

### What it is
A pseudonym is derived with HMAC-SHA256 under a secret key, with a **domain string** per purpose:

```
token = HMAC-SHA256(K_scope, domain ‖ 0x00 ‖ scope_id ‖ 0x00 ‖ label ‖ 0x00 ‖ normalise(value))
```

- **The same value in the same scope always gives the same token.** Joins, revisits and dialogue structure survive.
- **A different scope gives an unrelated token.** Pseudonyms do not link across scopes.
- **K comes from an environment variable** and must be at least 32 characters. It is never committed, logged or written to output. The manifest names only the key's *purpose*.
- **Why keyed:** the scorecard's "hashed ids reversible" check recovers unsalted MD5, SHA-1 and SHA-256 hashes by hashing candidate values. HETUs and phone numbers have small value spaces and can be enumerated. HMAC with a secret key defeats that attack.

### In free text (S2)
- Typed placeholders numbered in order of first appearance within the **conversation**: `[PERSON_1]`, `[PERSON_2]`, `[PHONE_1]`. "Oscar Lindberg" in turn 2 and "oscar" in turn 4 both become `[PERSON_1]`. A relative mentioned later becomes `[PERSON_2]`.
- **Normalisation** before keying:
  - fold case and strip separators;
  - convert spoken digits to digits;
  - remove Finnish and Swedish case endings from names (`Niemelän`, `Niemelälle` → `niemelä`);
  - link a first name alone to the full name already seen in the same conversation.
- **Per-scenario form:**

| Scenario | Form | Why |
|---|---|---|
| CS-S1 (external LLM vendor) | Typed placeholders, scoped per conversation | Target is no direct identifiers; consistent pseudonyms within a conversation are an explicit privacy target |
| CS-S2 (internal model training) | Deterministic **surrogates**: fake names and numbers of the same shape, chosen by HMAC from lists | "Surrogates preserve fluency better than [REDACTED]"; the model can't memorise real identifiers |
| CS-S3 (BPO audit) | Typed placeholders that keep the evidence ("agent asked for `[NATIONAL_ID]`"); `customer_id` dropped | The auditor must still see that verification happened |

**What this keeps:** who replied to whom, the intent signal (CS-U1), vocabulary (CS-U5), and the audit evidence.

### In tables (S1)
- **Release scope:** one key per release, with one domain per identifier type (`patient`, `visit`, `card`, `student`, `ip`...). Joins inside the release survive:
  - health `ed_visits` ↔ `lab_results` (revisit analysis);
  - education `student_id` across grades and absences (EDU-U4 needs the join);
  - cyber users and hosts across logs.
- **Recipient scope (innovation point):** the key is derived per recipient, `K_recipient = HKDF(K_master, recipient_id)`. If the vendor and the researcher both receive the data, they **cannot join their copies**. A whole class of linkage attack disappears at no utility cost to either recipient.
- Prefix-preserving IP pseudonyms where the scenario needs subnet structure (cyber), following B2.

### Demo moment (about 20 s)
1. The same conversation before and after: `[PERSON_1]` is still clearly the customer, and the reply structure is intact.
2. A join query on protected tables returns the same revisit rate as on the original.
3. Hash 10,000 candidate HETUs with SHA-256 and get zero matches against our tokens. Unsalted SHA-256 would have matched.

### Honest limits (put in the manifest)
- Pseudonymised data is still personal data under GDPR. CS-S1's own legal context says so.
- Placeholders keep the *count* of people mentioned in a conversation. That is a small amount of information we choose to release.
- Anyone who holds the key can re-link. Key custody is the controller's responsibility.

---

## 5. Pattern 2: closed release contract and fail-closed gate

### What it is
taskuMentor decodes its worker output against an exact allowlist: an unknown field is refused as forbidden content, and a missing field is refused as malformed. Nothing is "repaired" at the boundary. We apply the same idea to releases:

1. **The contract** is generated from the scenario policy. It lists the allowed files, the allowed columns per file, and the allowed **value form** per column:
   - age band `30-39` / `90+`;
   - postcode `201` or `201**`;
   - time rounded to the hour or week;
   - token = 64 hex characters;
   - text = redacted.
   Required columns are listed too, because removing what the scenario's utility tasks need is also a failure.
2. **The gate** runs on the transformed output **before** anything is published.

### Gate checks
| Check | What it catches | Why it matters |
|---|---|---|
| Allowlist of files and columns | Extra or renamed columns, withheld tables that should exist | Scorecard flaw C1 means renamed identifier columns are never scored; we catch them |
| Value-form check per column | A raw birth date in a column that should be a band; a minute-level timestamp in a column that should be hourly | Proves each generalisation actually happened |
| **Independent rescan** of every cell and every text field | HETU (checksum), IBAN (mod-97), cards (Luhn), email, phone, IP, MAC, plate, 32–64-character hex hashes, names from gazetteers | It uses different code from the detector, so a detector bug cannot hide itself. Scorecard does not score leftover technical identifiers. |
| Surviving original values | Any original direct-identifier value appearing anywhere in the output | Closes "we redacted the column but the name is in the notes" |
| k-threshold, only where the scenario requires it | Equivalence classes below k on the quasi-identifiers kept | Applied per scenario, not everywhere (`HACKATHON_PLAN` risk S1-1) |
| Row-map sanity, outside the release folder | Empty or partial row maps; a row map inside the release folder | Scorecard flaw C2 means bad row maps can fake zero risk; row maps must never be published |
| No empty tables, honest exit codes | Zero-row tables, missing paths | The scorecard treats these as success |

### Fail closed
- **High-severity hit** (NATIONAL_ID, PAYMENT_CARD, IBAN, SECRET, EMAIL, PHONE, any direct identifier, a contract violation): the **release is refused**. The exit code is non-zero, nothing reaches the release folder, and a refusal report is printed with counts by category and row or turn ids. The report contains no values.
- **Low-severity hit** (PERSON from a gazetteer, LOCATION, ORG in text): recorded as **residual risk** in the manifest instead of refusing, because name false positives are too common to block on. This is stated openly.
- **Atomic write:** build in a temporary folder, run the gate, then rename. A half-written release can never exist.

### Demo moment (about 25 s): the strongest beat
1. Corrupt one protected row live, for example paste a real card number into one turn.
2. Run the release: **REFUSED, 1 × PAYMENT_CARD, turn T0004821.** No files appear.
3. Line: *"Our gate refuses the release. The official checker exits 0 even when it finds hits, and it reports a missing path as clean."* This is a scorecard weakness confirmed in our QA (`HACKATHON_PLAN` §3.1). Mention it once, factually, and frame it as rigour, not mockery.

### Honest limits
- The gate is only as complete as its validators and gazetteers. An unknown name in free text can pass as a low-severity residual.
- The gate checks the *form* of the output, not the strength of an attack against it. That part is P3's measured risk.

---

## 6. Pattern 3: privacy manifest

### What it is
taskuMentor attaches a privacy manifest to every result:
- export assertions typed as literal `false` (no transcript, no quotes, no person identifiers...);
- the versions of every component;
- validator counts per category;
- the deletion status of temporary artifacts.

The manifest itself is scanned so that it cannot leak content. We produce one `privacy_manifest.json` per release.

### Contents
| Section | Contents |
|---|---|
| `release` | Dataset, scenario ID, recipient, trust level, creation time |
| `versions` | Detector, policy, transformer, gate, gazetteer, `pets-eval` |
| `inventory` | Per column: detected role, subtype, **reason** (for example "HETU checksum valid in 100% of non-empty values"); per text label: span counts |
| `pets` | Per column or label: the PET applied and its parameters (band width, rounding, k, ε, δ, unit of privacy, contribution bound, key scope) |
| `exportAssertions` + `assertionEvidence` | Flags that can only be `false` (`directIdentifiers`, `secrets`, `healthInText`, `rawTimestamps`, `reversibleHashes`, `keyMaterial`, `rowMaps`...), each with the check that proved it, the scan size and 0 hits. See "Every assertion is proved, not declared" below. |
| `gate` | Passed or refused, and counts per check and per category |
| `measured.privacy` | Scorecard risk components **before and after**, our exact-match span precision, recall and F2 per label, leakage before and after |
| `measured.utility` | Each required utility task **before and after**, plus composite scores, compared with B0, B2 and B2-k |
| `sacrificed` | Utility we chose to give up, and why (for example, "minute-level timestamps → hourly; CS-U4 handle time drops from 1.00 to 0.97") |
| `residualRisks` | Each with a measured rate and a plain-language note |
| `temporaryState` | Mapping tables kept in memory and destroyed; row maps written outside the release |

It contains **no data values**, only counts, parameters, versions and rates. The manifest is self-scanned by the gate's validators.

### Every assertion is proved, not declared

This is the part most teams won't have. Four rules:

1. **Closed manifest format.**
   - Each `exportAssertions` flag can only hold the value `false`, like the literal `false` types in taskuMentor.
   - An unknown key, a missing key, or any value other than `false` makes the manifest invalid. This is the same closed-contract logic as P2, applied to the manifest itself.
   - The writer has no code path that emits `true`. When a check fails, the outcome is a **refused release with a refusal report**, never a manifest that admits a leak.
2. **Each flag is bound to a check.** A flag is written only after its check has run on the final release folder and found 0 hits.
3. **Evidence sits next to the flag.** For each flag the manifest records the check that ran, its version, how many cells or spans it scanned, and the hit count (always 0 in a published release). The flag then reads as "checked 1,402,113 cells and 140,345 turns, 0 hits", not "we promise".
4. **Anyone can re-run it.** `pets-release verify <release_dir>` re-runs every bound check on the release and compares the results with the manifest. Judges, or the data recipient, can confirm the claims without trusting our pipeline run.

| Assertion (always `false`) | Check that proves it |
|---|---|
| `directIdentifiers` | Catalogued direct-identifier columns are absent or tokenised. The independent rescan finds 0 HETU, IBAN, card, email or phone hits in any cell or text. The surviving-original-values check finds 0 original identifier values anywhere. |
| `secrets` | 0 hits in the SECRET rescan (password, PIN and PUK cues; token URLs). 0 detected secret values survive. |
| `healthInText` (where the scenario requires it, e.g. CS-S1) | 0 hits in the health-lexicon rescan of text fields. 0 detected HEALTH spans survive. |
| `rawTimestamps` | Every time column matches the scenario's rounding form (hour or week). |
| `reversibleHashes` | Hashing a sample of original values with MD5, SHA-1 and SHA-256 recovers 0 tokens (the scorecard's own attack). |
| `keyMaterial` | The key, in raw, hex and base64 form, appears 0 times in the release or the manifest. |
| `rowMaps` | No `rowmap_*` file and no `protected_row` or `original_record_id` column in the release folder. |
| `quasiIdentifiersBelowK` (only when the scenario requires k) | 0 equivalence classes below k on the quasi-identifiers kept. |

Measured risks that cannot be reduced to 0, such as linkage rates and the rate of names outside the gazetteer, are **not** assertions. They go in `measured.privacy` and `residualRisks` with their numbers. Keeping proven absences separate from measured risks is what makes the manifest honest.

### Example (CS-S1; the numbers are placeholders until the pipeline runs)
```json
{
  "contractId": "pets.privacy-manifest", "schemaVersion": 1,
  "release": { "dataset": "customer_service", "scenario": "CS-S1", "recipient": "external-llm-vendor", "trust": "contractual" },
  "pets": {
    "text.PERSON":      { "pet": "pseudonymise", "form": "typed_placeholder", "scope": "conversation" },
    "text.NATIONAL_ID": { "pet": "redact", "form": "typed_placeholder" },
    "text.HEALTH":      { "pet": "redact", "form": "typed_placeholder" },
    "turns.ts":         { "pet": "round", "unit": "hour" },
    "conversations.customer_id": { "pet": "drop" }
  },
  "exportAssertions": { "directIdentifiers": false, "secrets": false, "healthInText": false, "rawTimestamps": false,
                        "reversibleHashes": false, "keyMaterial": false, "rowMaps": false },
  "assertionEvidence": {
    "directIdentifiers": { "check": "rescan.high_severity+surviving_values", "checkVersion": "0.3.0", "scannedCells": 0, "scannedTurns": 0, "hits": 0 },
    "healthInText":      { "check": "rescan.health_lexicon+surviving_spans", "checkVersion": "0.3.0", "scannedTurns": 0, "hits": 0 }
  },
  "gate": { "passed": true, "refusals": 0, "lowSeverityHits": { "PERSON": 0 } },
  "measured": {
    "privacy": { "freeTextLeakage": { "before": 0.80, "after": 0.00 },
                 "spanExactMatch": { "NATIONAL_ID": { "precision": 0.00, "recall": 0.00, "f2": 0.00 } } },
    "utility": { "CS-U1": { "before": 1.00, "after": 0.00 }, "CS-U5": { "before": 1.00, "after": 0.00 } }
  },
  "sacrificed": [ { "what": "turn timestamps rounded to hour", "task": "CS-U4", "before": 1.00, "after": 0.00 } ],
  "residualRisks": [
    { "risk": "names outside gazetteer", "measured": 0.00, "note": "single first names, nicknames" },
    { "risk": "template overlap", "measured": 0.85, "note": "headline metrics use a template-held-out split" }
  ],
  "temporaryState": { "mappingTablesPersisted": false, "rowMapsInRelease": false }
}
```

### The demo is the manifest
The dashboard is rendered **from** the manifest, so what we show is exactly what we can prove.

| Required demo item | Manifest section |
|---|---|
| 1. Data types identified | `inventory` |
| 2. PET per data type | `pets` |
| 3. Protected output | Release folder (linked) plus `gate` |
| 4. Utility before and after | `measured.utility` + `sacrificed` |
| 5. Sharing scenario | `release` + `exportAssertions` + `residualRisks` |

The pitch line comes from the kit itself: *"'Anonymised' and 'differentially private' are claims that need a method and parameters."* The manifest is where we state both.

---

## 7. Pattern 4: fully offline

### What it is
taskuMentor processes lesson audio on an isolated machine. Its sealing step runs with no network, and plaintext is wiped on every exit path. Our version:

- **No cloud model and no network calls.** Rules, validators, normalisers and gazetteers are local. An optional NER model is a local file.
- **Enforced, not promised:**
  - `--offline` is the default and replaces `socket.socket` with a function that raises;
  - a test runs the whole pipeline with networking blocked;
  - the demo can run in Docker with `--network none`.
- **Deterministic:** the same input, key and versions give byte-identical output. A test checks this, and it makes results reproducible for judges.
- **Temporary state:** pseudonym mapping tables live only in memory. Row maps are written outside the release folder for scoring only.

### Why judges care
- **CS-S1 is about data going to an external LLM vendor.** Our tool protects the data *before* it leaves, and it never sends anything anywhere itself, including to an AI service. A tool that redacts with a cloud LLM would create the very disclosure it is meant to prevent.
- A controller can run it inside their own environment with no new processor, no data transfer and no data processing agreement (DPA).

### Demo moment (about 10 s)
Turn Wi-Fi off and run the release, or show the blocked-network test going green. Line: *"No data leaves the machine. Not even to an AI model."*

---

## 8. The text redactor in brief (S2)

Detection order: high-severity validators first, then spoken numbers, then PERSON, then everything else. Measure after each step.

| Label | Technique | Trap |
|---|---|---|
| NATIONAL_ID | HETU regex plus checksum; spoken form after normalisation; partial codes after cue words | Split across turns (`070889 streck 965 2`); spoken separators (`viiva`, `streck`, `dash`) |
| PAYMENT_CARD, IBAN | Luhn; `FI` + mod-97; spoken forms | Prices are not cards |
| ACCOUNT_NUMBER | Cue words (`asiakasnumero`, `kundnummer`, "customer number") plus digit run | 11.6k spans; depends on context |
| PHONE | Finnish patterns; spoken digits; fragments across turns | Router IPs and prices |
| EMAIL | Regex plus reassembly of spelled-out emails | `piste`/`punkt`/`dot`, `at`/`ät` |
| PERSON | fi, sv and en name gazetteers plus names in the data; cue words (`nimeni on`, `jag heter`); agent and relative mentions | Common words that are also names; "Aava" and "Aallokko" are not PERSON |
| ADDRESS, LOCATION | Street suffixes (`-katu`, `-tie`, `-gatan`, `-vägen`); postcode plus town; town gazetteer | Only places that locate the person |
| HEALTH | Keyword lexicon (fi, sv, en) | Redact the phrase, keep the turn (CS-S1: "do not delete whole utterances") |
| SECRET, URL, IP, DEVICE_ID, USERNAME | Cue words (`salasana`, `PIN`, `PUK`, `lösenord`); token-bearing URLs; IMEI and ICCID | `192.168.1.1` is not personal |

---

## 9. Evidence and targets

- **Exact-match** span precision, recall and F2 per label. The scorer counts any overlap as a match, so predicting the whole document scores 1.0 (flaw C3). Show its numbers only alongside ours.
- **Leakage:** `pets-eval text --protected`. Baselines are 0.80 for turns and 0.83 for agent notes.
- **Utility:** the scenario's required tasks, scored with the **correct** scenario ID and valid row maps. Compare with B0, B2 and B2-k.
- **Generalisation** (85% of eval sentence skeletons also appear in train):
  - **headline:** a template-held-out split;
  - **zero-shot:** `education/counsellor_notes` and `health/clinical_notes`;
  - **hidden:** submit `pets_submission/customer_service_eval_redacted.csv` to the organisers' check.
- **Targets:**
  - CS-S1 recall ≥ 0.98 on NATIONAL_ID, PAYMENT_CARD, IBAN and SECRET (the scenario's own target);
  - leakage far below 0.80;
  - CS-U1 and CS-U5 at or above B2 (customer_service utility 0.86).
- **Pattern tests**, which double as demo evidence:
  - a planted card number is refused (P2);
  - an extra or renamed column is refused (P2);
  - the manifest self-scan passes and contains no values (P3);
  - a manifest with a `true`, unknown or missing assertion is rejected (P3);
  - `pets-release verify` re-derives every assertion from the release and matches the manifest, and it fails on a tampered release (P3);
  - the blocked-network run passes (P4);
  - two runs produce byte-identical output (P4);
  - candidate hashing recovers 0 tokens (P1).

---

## 10. Four-minute pitch (finals) and video

| Time | Beat | Pattern |
|---|---|---|
| 0:00–0:30 | Problem: "Dropping names isn't anonymisation. B0 still re-identifies 79% via receipts, and regex misses spoken ID numbers." | — |
| 0:30–1:10 | Detect and select: field inventory with reasons, live on `unseen`, then the PET per field for the chosen scenario | P3 inventory and PETs |
| 1:10–1:50 | Transform: the same conversation before and after (`[PERSON_1]` stays consistent); a join still works on protected tables | P1 |
| 1:50–2:30 | Gate: inject a card number and the release is refused. "We don't trust our own redactor; we verify it." | P2 |
| 2:30–3:20 | Proof: manifest dashboard. Every "no identifiers / no secrets / no health" flag shows the check behind it ("1.4M cells scanned, 0 hits"). Run `pets-release verify` live. Then risk before and after, utility before and after, what we sacrificed, and residual risks with numbers. Line: "Other tools claim. Ours can only say false, and proves it." | P3 |
| 3:20–3:45 | Offline: Wi-Fi off. "No data leaves the machine." | P4 |
| 3:45–4:00 | Close: "Patterns from our classroom-recording product, applied to nine domains. Protect the data, keep its value, and prove it." | All |

The demo video follows the same beats, with English narration. The dashboard must tell the story without narration.

---

## 11. Jury Q&A preparation (6 minutes)

| Likely question | Answer |
|---|---|
| "Isn't pseudonymised text still personal data?" | Yes, and the manifest says so. For CS-S1 we remove direct identifiers, secrets and health remarks, keep only consistent placeholders, and measure what leaks. We don't claim anonymity. |
| "How do you know the redactor generalises, given the templated data?" | 85% of eval sentence skeletons are in train, so we report a template-held-out split as the headline, zero-shot results on counsellor and clinical notes, and the organisers' hidden eval. |
| "Why should we trust your manifest?" | You don't have to. Each `false` names the check that proved it on the actual output, and `pets-release verify` re-runs those checks on the release in front of you. Its format can't even express `true`; a failing check refuses the release instead. Risks we can't prove to be zero are listed separately, with measured rates. |
| "What if your gate misses something?" | The gate uses independent validators, not the detector's code. Names outside the gazetteer are the known gap, and they are reported as residual risk with a measured rate. |
| "Why not an LLM for redaction?" | Sending data to a cloud LLM in order to protect it from an LLM vendor defeats the purpose. A local NER model fits P4 [if built by the Sat 12:00 cut-off]. |
| "Why not k-anonymity everywhere?" | B2-k drops utility to 0 on several scenarios. k is applied where the threat model calls for it, and every trade-off is in `sacrificed`. |
| "Who holds the key?" | The controller. Keys are scoped per recipient, so two recipients can't join their copies, and key material is never in the output (an `exportAssertions` flag). |
| "Did you just optimise the scorecard?" | No. We found scorecard weaknesses (overlap-based span scoring, unvalidated row maps, errors that report success), guarded against them, and report exact-match metrics. |

---

## 12. Honest limitations (shown in the demo, also in the manifest)

- The data is synthetic and templated. Real speech and notes are messier.
- Rule-based PERSON recall is bounded by the gazetteer. Nicknames and rare names can leak, and the rate is reported.
- Health redaction is lexicon-based and misses indirect remarks.
- The gate checks the form of the output. Attack resistance is measured against the kit's attackers and the organisers' hidden ones, not proven in general.
- Pseudonymisation is not anonymisation, and the key holder can re-link.
- Languages covered: Finnish, Swedish, English.

---

## 13. Build order

Fits the timeline in `HACKATHON_PLAN.md` §8.

| # | Ticket | Pattern | Done when |
|---|---|---|---|
| 1 | Offline guard + determinism harness | P4 | The blocked-network test and byte-identical test are green on a stub pipeline |
| 2 | Pseudonym module (HMAC, domains, scopes, recipient keys) | P1 | Joins survive on health or education; candidate hashing recovers 0 tokens |
| 3 | Rules redactor v1 (validators, spoken numbers, spelled emails, cross-turn stitching) | S2 | Exact-match recall measured against the 0.80 leakage baseline |
| 4 | Contract generator + gate + atomic write | P2 | The planted-card and renamed-column tests refuse |
| 5 | Manifest builder (closed format, each assertion bound to a check, evidence) + self-scan + `pets-release verify` + dashboard renderer | P3 | The dashboard shows all five required demo items from the manifest alone; `verify` passes on a good release and fails on a tampered one |
| 6 | PERSON and HEALTH layers; per-scenario policies CS-S1/S2/S3 | S2, P1 | Targets in section 9 met or the gap reported |
| 7 | Tabular scenario through the same gate and manifest | S1, P2, P3 | Scorecard run with the correct ID; B0/B2/B2-k comparison in the manifest |
| 8 | `pets_submission/` (eval redactions, `unseen` labels, tables with row maps) | — | Submitted Saturday afternoon for the hidden checks |

**Cut-offs:**
- NER go/no-go at **Sat 12:00**.
- Feature freeze at **Sat ~20:00**.
- If time runs short, cut CS-S2 surrogates first (placeholders are enough), then recipient-scoped keys. Release scope is enough for the demo.

---

## 14. Repo hygiene for a public submission

- `.gitignore` covers `rowmap_*`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, `.venv/` and any key files.
- The HMAC key is never committed; the demo uses a generated throwaway key.
- No row maps in the release folder or the public repo. P2 checks this, and P3 asserts it.
- No private taskuMentor code or paths in the submission. Only the patterns are described.
