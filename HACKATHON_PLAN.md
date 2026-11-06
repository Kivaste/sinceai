# TrustED PETs Transformer: hackathon plan

Since AI Hackathon 2026, Turku, 6–8 November 2026.
Written Friday 6 Nov, about 23:00 EET. Build opened Fri 19:30. **Hard deadline: Sun 8 Nov 10:00 EET** (sinceai.app).

---

## 1. The challenge in one page

**Brief:** build a working tool that applies privacy-enhancing technologies to sensitive synthetic data while keeping it useful for analysis. "Protect the data, keep its value."

**Required objective:** Detect → Select → Transform → Demonstrate.

**The final demo must show:**
1. The data types identified in the original dataset.
2. The PET selected for each data type.
3. The transformed dataset, or a protected view of it.
4. Utility before and after the transformation.
5. The sharing scenario the protected data is fit for.

**Judging** (Since AI criteria; there is no weighted rubric):

| Criterion | What it means here |
|---|---|
| Technical implementation | Correct, reliable PET choices |
| Innovation | An intelligent, explainable approach |
| Impact | Evidence that disclosure risk went down while analytical utility was kept |
| Presentation | A clear scenario, a before/after comparison and honest limitations |

**Submission:** in sinceai.app. One working prototype, a short demo video (English narration recommended), a description and the repo. Never include real sensitive data or secrets.

**How winners are picked:**
- The company (TrustED) picks the top 3 for this challenge.
- Five finalists across all challenges are chosen by participant vote. Each gives a 4-minute pitch followed by 6 minutes of jury Q&A.

**Sources:** `Briefs/Challenge_TRUSTED_PETs_Transformer_EN (1) (1).pdf`, `Briefs/TrustED_PETs_Transformer_Challenge_Brief_FINAL_REVIEW (1).docx`, the kit's `START_HERE.md`, and https://sinceai.ai/hackathon-2026/guide.

---

## 2. The kit (TRUSTED_PETS_PROVING_GROUND_2026)

**Contents:**
- 9 synthetic datasets plus 1 unlabelled `unseen` dataset, all drawn from one population of 100k people in Southwest Finland: 4.74M rows, 475 catalogued columns, 353,893 labelled PII spans, 27 sharing scenarios (3 per dataset), 13 attacker-knowledge files.
- `pets-eval` toolkit: a **self-assessment** scorecard. It is not the judging score.
- Baselines B0–B4 with their results in `docs/BENCHMARK.md`.

**Optional organiser checks** (`docs/EVALUATION.md`). Put a `pets_submission/` folder in the repo containing:
- `unseen_field_labels.csv`, scored against private labels;
- `customer_service_eval_redacted.csv` (`turn_id,text`) or `customer_service_eval_spans.jsonl`, scored against the private gold spans of the eval split (2,962 conversations);
- the protected tables with their row maps, one subfolder per dataset, tested against a stronger hidden attacker.

**Baselines to beat:**

| Baseline | Key numbers |
|---|---|
| B1 detection | macro-F1 0.65; sensitive_attribute F1 0.16 (recall 0.10); quasi_identifier 0.67; direct_identifier 0.86 |
| B2-k (k ≥ 5) | Utility collapses in many scenarios: HEALTH-S2 0.00, FIN-S1 0.06, CITY-S3 0.00 |
| B3 DP | 0.69 utility at ε = 1; 0.80 at ε = 2 |
| B4 synthetic | 0.38 utility |

**Free-text leakage is the biggest measured risk**, even under B2-k: health clinical_notes 0.88, customer_service turns 0.80 and agent_note 0.83, finance transfers.message 0.71. `BENCHMARK.md` itself says free text is "where most teams can win".

**Worst re-identification under B2:** health 0.10, finance 0.00 (0.79 under B0, via shared receipts). B2-k brings it to 0.00 everywhere.

---

## 3. QA findings that affect us

### 3.1 `pets-eval` scorecard defects. Do not exploit them; guard against them.
- **C1:** identifiers are found only by their original column name, so renamed identifier columns are never scored.
- **C2:** row maps are trusted without validation. An empty or partial map gives linkage risk 0.
- **C3:** span scoring counts any prediction that overlaps a gold span as correct, so predicting the whole document scores F1/F2 = 1.0. Report exact-match metrics instead.
- **Scenario IDs aren't validated.** A wrong or invalid ID inflates utility (0.79 → 0.98) and lowers risk. Always pass the correct ID.
- **A table that throws an error silently drops its risks.** A zero-row table triggers this.
- **Leftover technical identifiers and regex hits aren't scored.** For example, about 40k IPs in a raw copy of `dns_logs` counted as no risk.
- **Synthetic-data checks are buggy.** The exact-copy check uses the wrong denominator (a raw copy scored 0.048), and H-U3 doesn't use the holdout.
- **Errors look like success.** A missing path exits 0 and writes an empty scorecard, `check` on a missing path reports "clean", and `check` exits 0 even when it finds hits.
- **Windows problems:**
  - `pets-eval detect` crashes when not run from the kit root. Use `--root` or set `PETS_ROOT`.
  - The scorecard crashes when its output is piped (Δ, → and ≥ hit the cp1252 encoding). Set `PYTHONUTF8=1`.
- **The quickstart's own HMAC pseudonyms trigger PHONE false positives in `check`.**

**Implication:** we need our own verification step. It should catch renamed identifier columns, leftover IPs, MACs and hashes, check that row maps are valid and complete, and score spans by exact match. That step is also a selling point in the demo.

### 3.2 Data
- Overall the data is clean: the manifest and its SHA-256 hashes match, the headline counts hold, and no hidden labels leak.
- Read every CSV with `dtype=str`.
- **Data-quality traps** (handle them; they are worth mentioning in the demo):
  - 66 ED visits have discharge before arrival;
  - 1% of `service_requests` timestamps use the `d.m.yyyy hh.mm` format;
  - 30 orphan shared-mailbox UPNs in the cyber sign-in logs;
  - 1,086 lab results fall after discharge.
- **`unseen` dataset** (26 columns, 2,818 rows):
  - it mixes HETU and date formats and uses decimal commas;
  - `c16` holds sick-leave reasons, which are Art. 9 health data;
  - `c20` is a 40-hex hash, probably a pseudonym with 700 distinct values, matching `c02`;
  - there are about 4 rows per employee, so count k **per person**, not per row.
- **Text templates repeat:** 85% of eval-turn sentence skeletons also appear in train. Hidden-eval F2 will therefore be high for everyone, so it doesn't set you apart.

### 3.3 Housekeeping
- **Never commit `rowmap_*.csv`.** `results/quickstart/rowmap_ed_visits.csv` is currently untracked, and the repo has no `.gitignore`. Add one that ignores `rowmap_*`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/` and `.venv/`.
- **Test environment:** a scratch venv is at `%TEMP%\pets_qa_venv` (Python 3.14, pandas 3.1.1). All 21 kit tests pass.

---

## 4. Chosen solution: S1 core + lean S2 redactor

Three options were proposed from the challenge owner's perspective and red-teamed by a critic agent. The critic ranked them **S1 > S2 > S3** and recommended a combination.

### 4.1 S1: Scenario-driven PET compiler (the core)

| Stage | What it does |
|---|---|
| Detect | Column-name rules plus value profiling: HETU checksums, IBAN mod-97, Luhn, email, IP, MAC, plate, phone, cardinality, entropy, date parsing. A semantic step (keywords or a local LLM) handles sensitive attributes and quasi-identifiers, where B1 is weakest. Every column gets a **reason**. |
| Select | A policy maps the scenario's trust level, threat model and required utility tasks to a PET per column. **Whether k-anonymity applies is a per-scenario decision, not a default.** |
| Transform | Keyed HMAC pseudonyms that stay consistent across tables, so joins and revisits survive. Plus generalisation, suppression, rounding and prefix-preserving IPs, using a few hand-designed generalisation options per scenario rather than a general optimiser. |
| Verify | Our own checks (section 3.1) plus the `pets-eval` scorecard with the correct scenario ID. Report the risks that remain. |
| Demo | One tabular scenario in depth, plus live detection on `unseen`. |

### 4.2 S2: Lean free-text redactor (the free-text PET inside S1)
- **Rule-based:**
  - validators for HETU, IBAN, cards, emails, IPs and phones;
  - normalisers for spoken numbers in Finnish, Swedish and English;
  - reassembly of spelled-out emails;
  - stitching of identifiers split across turns;
  - name lists and gazetteers.
- **Consistent typed placeholders** within a conversation (`[PERSON_1]`), so the intent and vocabulary tasks (CS-U1, CS-U5) survive.
- **Policy per scenario:** CS-S1 (external LLM vendor) gets maximum redaction; CS-S3 (outsourced BPO audit) keeps consistent placeholders.
- **Applied to:** customer_service turns and agent notes, health clinical_notes, finance transfers.message.
- **Reported with exact-match precision, recall and F2**, plus a template-held-out split and zero-shot results on clinical notes. Eval redactions are submitted to the organisers.

### 4.3 Cut list
- NER fine-tuning. **Hard cut-off Sat 12:00**: only if the rules are already done and it's working by then.
- The public_admin extension.
- A general-purpose generalisation optimiser (use hand-designed options instead).
- All of S3 except reusing B3 with its mechanism stated (ε, δ, unit of privacy, contribution bound), so the H-DP task isn't scored 0.

---

## 5. Risks from the critic, with mitigations

| # | Risk | L / I | Mitigation |
|---|---|---|---|
| S1-1 | Forcing k ≥ 5 everywhere kills the utility the scenarios need. B2-k scores 0 on H-U6, H-U7 and H-U8, and FIN-U1 drops from 1.00 to 0.12. | H/H | The policy decides per scenario. FIN-S1: keyed tokens plus minute-level time, argued against the receipt attack (0.79 → 0.00). Health: consistent HMAC keys for patients and visits across ed_visits and lab_results. |
| S1-2 | Without text redaction, privacy stays around 0.5. | H/H | S2 is the free-text PET in every demo. |
| S1-3 | Validators only solve the easy column types. | M/M | A semantic step for sensitive attributes and quasi-identifiers. Measure macro-F1 against B1's 0.65 with tables held out, and submit the `unseen` labels. |
| S2-1 | The template overlap inflates F2 for everyone, and judges will ask about real text. | H/M | Report a template-held-out split and zero-shot clinical-notes results as the headline. |
| S2-2 | Fine-tuning plus three languages doesn't fit in the time. | M/H | Rules first; NER only by the Sat 12:00 cut-off. |
| S2-3 | A redactor alone shows only one technique. | M/H | It runs inside S1 with a different policy per scenario. Report precision so over-redaction can't be hidden. |
| S3-1 to S3-3 | Little room to improve on DP, contribution bounding introduces bias, and the scorecard evidence is weak. | M/H | Cut S3. Keep B3 only, with its mechanism stated. |
| **Biggest** | Optimising the self-assessment scorecard instead of the scenario. | n/a | Pick PETs from each scenario's threat model, back them with our own verification and the hidden checks, and state what was sacrificed. |

Correction to the critic: it claimed linkage risk is "0.00 under B2 everywhere". Health is 0.10 under B2; only B2-k reaches 0. The conclusion that free text matters most still holds.

---

## 6. Demo storyboard (all five required items)

1. **Field inventory:** role, subtype and a reason per column, including the live `unseen` detection.
2. **PET per field**, tied to the scenario's threat model and legal context, with a short line explaining each choice.
3. **Protected output:** real files and a protected view, not screenshots.
4. **Before and after:**
   - utility on the scenario's required tasks;
   - privacy risk components;
   - free-text leakage of 0.88 → ours;
   - comparison with B0, B2 and B2-k.
5. **Sharing scenario**, plus the **residual risks we state ourselves**: which attacks still work and at what rate, plus the scorecard bugs we found and guarded against.

**Pitch hooks:**
- "Removing names isn't enough: B0 still re-identifies 79% via receipts."
- "Regex misses spoken numbers and spelled-out emails; we don't."
- "Our verification step catches what the official scorecard misses."
- "Data never leaves the machine: no cloud model."

The finals slot is 4 minutes, so the dashboard has to tell the story without narration.

---

## 7. Workflow (Matt Pocock skills)

1. `/compact` at this boundary, with an instruction to keep this plan's decisions.
2. `/setup-matt-pocock-skills`, once. Tracker: GitHub Issues (`Kivaste/sinceai`) if teammates pick up tickets, local `.scratch/` if solo.
3. `/grill-with-docs`, time-boxed to **about 30 minutes**. Settle:
   - team size and roles, including the video owner;
   - the tabular scenario (HEALTH-S1 or FIN-S1) and the customer-service scenario;
   - the UI (CLI plus HTML dashboard, or a small web app);
   - a local model or not;
   - the exact scope of the verification checks.
4. Skip the prototype detour. The rules-only redactor measured against the 0.80–0.88 leakage figures becomes **ticket 1**.
5. `/to-spec` → `/to-tickets` in the same context window, with no compaction in between.
6. `/implement-spec`: parallel tickets, built test-first, on one integration branch, ending with a code review.
7. `/retro` after the event.

---

## 8. Timeline (EET)

| When | Milestone |
|---|---|
| Fri 23:00–23:30 | Compact, setup, grilling |
| Fri ~00:00 | Spec and tickets published; implementers running |
| Sat 09:00–12:00 | **Challenge-partner Q&A at Joki.** Ask TrustED about the hidden checks and report the scorecard bugs (it shows rigour and builds goodwill). |
| **Sat 12:00** | NER go/no-go cut-off |
| Sat afternoon | `pets_submission/` ready; ask the organisers to run the hidden checks |
| **Sat ~20:00** | Feature freeze; only fixes and docs after this |
| Sat night | Dashboard polish, README, limitations section |
| Sun 06:00–08:30 | Record the demo video (English narration), write the description |
| **Sun 09:00** | Submit in sinceai.app (an hour of buffer) |
| **Sun 10:00** | Hard deadline |
| Sun 13:15–15:30 | Closing ceremony, top 3 per challenge, finals |

---

## 9. Submission checklist
- [ ] Working prototype in the repo; README with run instructions that work on Windows (`python`, not `python3`)
- [ ] Field inventory, PET-per-field table, protected outputs, before/after utility, scenario, residual risks
- [ ] Scorecards run with the **correct** scenario IDs and **valid** row maps
- [ ] Our own verification report (exact-match span metrics; checks for renamed identifiers and leftover identifiers)
- [ ] `pets_submission/`: `unseen_field_labels.csv`, customer_service eval redactions or spans, protected tables with row maps
- [ ] **No `rowmap_*.csv` in public materials or the public repo**, no secrets, HMAC key not committed
- [ ] Demo video (short, English narration), description, presentation
- [ ] An honest limitations section (template text, the simplified attackers, what we sacrificed per scenario)
