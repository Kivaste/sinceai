# sinceai: purpose-first PETs

Team project for the **TrustED PETs Transformer** challenge at Since AI Hackathon 2026 (Turku, 6-8 Nov 2026).
**Submission deadline: Sunday 8 Nov, 10:00 EET (fixed), on sinceai.app.**

> Release only what the purpose needs, at the coarsest detail that still serves it, and prove both the privacy and the utility.

`pets-release` is an offline, deterministic command-line tool. Give it a sharing scenario and the source data. It builds a protected release, runs a fail-closed gate over it, and writes a signed privacy manifest. Anyone holding the release can re-run the release-derivable checks. Terms follow [GLOSSARY.md](GLOSSARY.md).

## Quick start (Windows, PowerShell)

Requirements: Python 3.10 or newer on `PATH` as `python` (the project uses 3.14), and the challenge kit. The kit is never committed: it lives in `Briefs/` (gitignored) or wherever you unpacked it.

Use the venv executables directly: no activation or execution-policy change is needed,
even under PowerShell's default `Restricted` policy.

<!-- docs-test: skip reason=environment-setup -->
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -m pip install -e ".[dev,eval]"
.\.venv\Scripts\python.exe -m pip install -e "Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026\toolkit"
```

The interpreter check must print this clone's `.venv\Scripts\python.exe`, not a system Python.

Settings come from the environment. Nothing is read from a file, and nothing is written back.

| Variable | Used for | Rule |
|---|---|---|
| `PETS_KIT` | Path to the kit root (the folder holding `data/`, `metadata/`, `docs/`) | Or pass `--kit` |
| `PETS_HMAC_KEY` | Master key for pseudonyms and the manifest signature | At least 32 characters, else exit 2. Never commit it, never paste it into a log |
| `SOURCE_DATE_EPOCH` | Creation time as Unix seconds | Or pass `--created`. If neither is set, exit 2 |

<!-- docs-test: skip reason=sets-secret-placeholder-only -->
```powershell
$env:PYTHONUTF8 = "1"
$env:PETS_KIT = "<path to the kit root>"
$env:PETS_HMAC_KEY = "<at least 32 characters, from your own secret store>"
$env:SOURCE_DATE_EPOCH = "1793000000"
```

Check that the install works and that the kit is readable (these print table names, row counts and input digests, no values):

<!-- docs-test: run -->
```powershell
.\.venv\Scripts\pets-release.exe --help
.\.venv\Scripts\pets-release.exe kit-info --dataset health --kit "$env:PETS_KIT"
```

In the later examples, use `.\.venv\Scripts\pets-release.exe` wherever they say
`pets-release`; activation is not required.

Exit codes: `0` success; `1` refusal or verify failure; `2` usage error or unknown state. Unknown counts as failure.

## Demo

The demo has three parts: HEALTH-S1 (ED visits to a university research group) in depth, CS-S1 (contact-centre transcripts to an LLM analytics vendor) for free text, and live detection on the `unseen` export.

### 1. Live detection on `unseen`

<!-- docs-test: run -->
```powershell
pets-release detect unseen --out ..\sinceai-out\unseen_field_labels.csv --format unseen --kit "$env:PETS_KIT"
```

### 2. HEALTH-S1 release

`--created` pins the creation time. The same input, key, creation time and tool versions give a byte-identical release.

<!-- docs-test: run -->
```powershell
pets-release run --scenario HEALTH-S1 --out ..\sinceai-out\health-s1 --created 2026-11-07T08:00:00Z --kit "$env:PETS_KIT"
```

<!-- docs-test: skip reason=cs-s1-run-needs-ticket-23 -->
```powershell
pets-release run --scenario CS-S1 --out ..\sinceai-out\cs-s1 --created 2026-11-07T08:00:00Z --kit "$env:PETS_KIT"
```

A release folder holds one `<table>.csv` per released table and `privacy_manifest.json`, nothing else. The gate refuses any other file. If a check finds a high-severity violation, errors or does not run, the tool exits 1, prints counts by check and label (never values), and publishes nothing.

### 3. Verify, in two tiers

Recipient mode needs only the release folder. It re-runs every release-scope check, recomputes file digests and validates the manifest against the schema. Its success line always says **limited**:

```text
VERIFIED (limited): N release-checked, M producer-attested
```

<!-- docs-test: run -->
```powershell
pets-release verify ..\sinceai-out\health-s1
```

Controller or auditor mode (`--full`) also needs the kit and the key. It re-runs every check in the registry, including the producer-scope ones (original-value survival, reversible hashes, key material, per-person k), the input digests, the tool revision and the signature. Any check that cannot run is a failure.

<!-- docs-test: run -->
```powershell
pets-release verify --full --kit "$env:PETS_KIT" ..\sinceai-out\health-s1
```

| | `verify <release>` (limited) | `verify --full --kit <path>` |
|---|---|---|
| Who | Recipient, anyone holding the folder | Controller or auditor with the key |
| Needs | Release folder | Release folder, kit, `PETS_HMAC_KEY` |
| Checks | Release-scope only | Release and producer scope, signature, input digests, tool revision |
| Success line | `VERIFIED (limited): N release-checked, M producer-attested` | Full verification |
| Unavailable check | Counted as producer-attested | Failure |

Limitation: digests catch accidents only. Someone who edits a release can recompute them. Only `--full` checks the signature, and only the key holder can run it.

### 4. Dashboard

A static HTML file rendered from the manifest alone. No network assets and no row values.

<!-- docs-test: run -->
```powershell
pets-release dashboard ..\sinceai-out\health-s1 --out ..\sinceai-out\health-s1-dashboard.html
```

### 5. Submission bundle

The bundle goes to `..\sinceai-out\pets_submission`, outside every repo. A complete bundle (both target scenarios) is the default:

<!-- docs-test: skip reason=complete-bundle-needs-cs-s1-release -->
```powershell
pets-release submission --out ..\sinceai-out\pets_submission --release ..\sinceai-out\health-s1 --release ..\sinceai-out\cs-s1 --kit "$env:PETS_KIT"
```

Without a CS-S1 release it refuses (`REFUSED: incomplete`). A partial bundle needs `--partial`; it prints `SUBMISSION BUILT (PARTIAL)` and lists the missing datasets in `submission_index.json`:

<!-- docs-test: run -->
```powershell
pets-release submission --partial --out ..\sinceai-out\pets_submission_partial --release ..\sinceai-out\health-s1 --kit "$env:PETS_KIT"
```

## Where row maps go

Row maps (`rowmap_<table>.csv`) are scoring aids, not part of a release. They are written to `<out>.scoring/`, next to the release folder, never inside it. The same folder holds raw scorecard output, the search log and refusal reports.

They must never enter the public repo (decision D15, [ADR 0003](docs/adr/)). The organisers receive them only through the private repo `Suhtetark-Kool/trusted-since-ai`. `pets_submission/` is built outside this repo for that purpose. `.gitignore` already excludes `Briefs/`, `rowmap_*.csv`, `truth/`, `pets_submission/` and `.env`; do not force-add them.

## Reproducibility

- Same input, key, `--created` (or `SOURCE_DATE_EPOCH`) and tool versions give a byte-identical release. Rows and lists are sorted; the only time value is the creation time.
- Run Python with `PYTHONUTF8=1`, `PYTHONDONTWRITEBYTECODE=1` and `TZ=UTC`.
- The tool blocks network sockets at start-up, and subprocesses inherit the block.
- Every CSV is read with `dtype=str`. Never let pandas infer types.
- Running the tests:

<!-- docs-test: skip reason=runs-the-whole-test-suite-recursively -->
```powershell
$env:PYTHONUTF8 = "1"; $env:PYTHONDONTWRITEBYTECODE = "1"; $env:TZ = "UTC"
python -m pytest -n auto --import-mode=importlib tests
```

Tests marked `kit` need `PETS_KIT` and are reported as not run when it is absent.

## Documentation

| Doc | What's in it |
|---|---|
| [docs/setup.md](docs/setup.md) | Local environment, `pets-eval` toolkit, repo hygiene |
| [docs/challenge.md](docs/challenge.md) | The challenge, the data package, deadlines, how judging works |
| [docs/concept.md](docs/concept.md) | Our angle: purpose-first data minimisation, and why it differentiates |
| [docs/tool-spec.md](docs/tool-spec.md) | The tool: pipeline, components, inputs and outputs |
| [docs/evaluation-strategy.md](docs/evaluation-strategy.md) | How we measure ourselves without overfitting |
| [docs/build-plan.md](docs/build-plan.md) | Sequencing, checkpoints, workstreams, risks |
| [docs/decisions.md](docs/decisions.md) | What's decided and what's still open |
| [HACKATHON_PLAN.md](HACKATHON_PLAN.md) | Engine and proof: scenario compiler, free-text redactor, timeline |
| [PRIVACY_PATTERNS_PLAN.md](PRIVACY_PATTERNS_PLAN.md) | Keyed pseudonyms, fail-closed gate, privacy manifest, offline |
| [docs/adr/](docs/adr/) | Architecture decision records |
| [docs/decision-log.md](docs/decision-log.md) | Append-only execution log kept by the orchestrator |
| [AGENTS.md](AGENTS.md) | Steering file for agents: hard rules, tracker, domain docs |
| [GLOSSARY.md](GLOSSARY.md) | Shared vocabulary |

## Repo layout

```
Briefs/                 challenge briefs + data package (NOT committed)
docs/                   planning, specs, decisions
src/pets_release/       the tool (CLI: pets-release)
src/pets_attacker/      validation-only attacker (the only code allowed to read truth/)
tests/                  pytest suites; tests/docs checks this README
GLOSSARY.md             project vocabulary
```
