# Tool spec

Status: architecture **decided** (option D, "hybrid"). Details marked _open_ are still to be settled; see [decisions.md](decisions.md). Terms are defined in [GLOSSARY.md](../GLOSSARY.md).

## Pipeline

```
data request (plain language)
   │
   ▼
[1] Understand ──► needs spec + purpose checks        (LLM, strict schema, human approves)
   │
   ▼
[2] Detect ──────► column roles for the source tables (needed for fields the request doesn't mention)
   │
   ▼
[3] Choose form ─► release form: rows / aggregates / synthetic   (rule table from trust level + purpose)
   │
   ▼
[4] Minimise ────► constrained search down each field's detail ladder
   │                 constraint: every purpose check passes
   │                 goal:       minimise the worst risk component
   ▼
[5] Transform ───► release (tables/views) + rowmaps (never published)
   │
   ▼
[6] Verify ──────► pets-eval scorecard + our own attacker + residual-identifier check
   │
   ▼
[7] Report ──────► field justifications, before/after, trade-off chart, residual risks, "fit for / not fit for"
```

## Components

### 1. Understand: request → needs spec + purpose checks

- **Input:** data request text; the dataset's data dictionary (column names, descriptions, types; from the package's `docs/DATA_DICTIONARY.md` or derived by our detector).
- **Output: needs spec** (strict JSON schema, validated against the dictionary) — example:

```json
{
  "request": "Researcher studying ED crowding and revisits",
  "recipient_trust": "controlled_research",
  "fields": [
    {"table": "ed_visits", "field": "arrival_ts", "detail": "week",
     "why": "Crowding and revisit trends are weekly; no analysis needs the minute."},
    {"table": "ed_visits", "field": "patient_hetu", "detail": "keyed_pseudonym",
     "why": "Revisits require linking a patient's visits; the identity itself is not needed."},
    {"table": "ed_visits", "field": "date_of_birth", "detail": "withheld",
     "why": "Age band (derived) is enough for revisit rate by age."}
  ],
  "derived_fields": [{"name": "age", "from": ["date_of_birth", "arrival_ts"], "detail": "10y_band"}]
}
```

- **Output: purpose checks.** Executable analyses run on both the original and the release, each producing an agreement score in [0, 1]. Example: "median length of stay by triage level", "30-day revisit rate by age band".
  - _open:_ representation. Options: generated pandas code run in a sandbox, or a small fixed vocabulary of analysis types (group-by aggregate, rate, correlation, time curve) with parameters. The vocabulary is safer and faster to validate.
- **Human in the loop:** the needs spec is shown for approval and edits before anything is released.
- **Self-check:** for the 27 packaged scenarios, compare our generated purpose checks with the scenario's official utility tasks (alignment score: e.g. "recovered 4 of 5 required analyses").

### 2. Detect: column roles

- Classify each column as one of: `direct_identifier`, `quasi_identifier`, `sensitive_attribute`, `technical_identifier`, `free_text`, `record_key`, `non_sensitive` (the package's taxonomy).
- Signals: column name, value patterns (Finnish personal ID (HETU), IBAN, phone, email, IP, MAC, plate), cardinality and uniqueness, optional LLM pass.
- **Must not read `metadata/field_catalog.csv` at runtime.** That file is the answer key, used only for scoring (`pets-eval detect`). Baseline to beat: B1 macro-F1 0.65.
- Needed because the request never mentions identifiers, but the tool must still know which fields are dangerous and which free-text fields need redaction.

### 3. Choose form: release form

Initial rule table (_open_, to be refined against the scenarios):

| Trust level | Default form | Exceptions seen in the scenarios |
|---|---|---|
| `public` | Aggregate tables (small-cell suppression or DP with stated ε) | — |
| `contractual` | Pseudonymised rows, k-checked | Model-training purposes → synthetic (HEALTH-S3, FIN-S2) |
| `controlled_research` | Pseudonymised rows, k-checked | — |
| `internal` | Pseudonymised rows, light coarsening | — |

### 4. Minimise: constrained search over detail ladders

- **Detail ladders per field type** (about three levels each is enough):

| Field type | Ladder |
|---|---|
| Timestamp | exact → hour → month+hour → day → week → month → withheld. Branch rung `ts.hour_of_day` (date-free `HH:00`): coarser than month+hour and everything finer, but **not comparable** with day/week/month (it drops the date, they drop the hour). A plan or floor pairing it with a date rung is refused. From month+hour the search walks the date branch (day → week → month) and the hour-of-day branch independently, every step measured; it adopts the better branch end (lower risk, else the date branch on a tie) and never moves between the two. |
| Birth date / age | date → year → 5y band → 10y band (top-coded) → withheld |
| Location | coordinates → 3 decimals → 2 decimals → postcode 3-digit → municipality → withheld |
| Postcode | 5-digit → 3-digit (`201**`) → withheld |
| Code (ICD-10, etc.) | full → 3-char → group/chapter → withheld |
| Identifier | keyed pseudonym (HMAC) → random token (breaks joins) → withheld |
| Numeric measure | exact → rounded → binned → withheld |
| Free text | redacted (spans masked) → withheld |

- **Rule:** every purpose check ≥ threshold (_open_: e.g. 0.9). Within that, minimise the **worst** risk component, then the mean.
- Start from the needs spec's proposed levels and coarsen step by step. Evaluate **joint** moves for quasi-identifiers (k-anonymity is computed over the combination). Add local suppression as a last step to reach k ≥ 5.
- Run the search on a **sample** for speed; confirm on the full data.
- **Every step is logged** (field, level tried, risk components, check scores, accepted/rejected, reason). That log is the raw material for the field justifications and the trade-off chart.

### 5. Transform

- Standard operations: HMAC keyed pseudonyms (key never committed), generalisation, rounding, suppression, aggregation, free-text redaction.
- **Free-text redaction is a key quality lever** (the benchmark says this is where teams win): catch names, spoken numbers, spelled-out emails, addresses and IDs, not just regex patterns. Measure with `pets-eval text` (F2 favours recall).
- Output layout follows `pets-eval` conventions: same table file names, original column names for kept columns, `rowmap_<table>.csv` for scoring only.

### 6. Verify

See [evaluation-strategy.md](evaluation-strategy.md). In short: `pets-eval scorecard` (inside the loop), our own attacker (outside the loop), `pets-eval check` for leftover direct identifiers.

### 7. Report

- One page per release: the request, the needs spec with justifications, the release form and why, before/after risk components, purpose-check scores, attacker results, residual risks, and "fit for / not fit for".
- _open:_ format. Options: an HTML report from the CLI, or a small web UI. This depends on team size.

## Non-goals (for this weekend)

- A general-purpose optimiser. A few ladder levels per field type is enough.
- Covering all 27 scenarios in depth. One lead scenario in depth, plus a second one to show the tool generalises.
- Trusting the LLM without checks. Everything it produces is validated and approved by a person.
