# Setup

## Python environment

The `pets-eval` toolkit is installed into a project-local virtualenv at `.venv/` (Python 3.14 on the first machine; the toolkit needs ≥ 3.10, numpy, pandas 2/3, scipy, scikit-learn).

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e "Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026\toolkit"
.\.venv\Scripts\Activate.ps1
```

On Windows, set `$env:PYTHONIOENCODING="utf-8"` first; some output contains non-ASCII characters.

Run `pets-eval` commands **from the package root** (the folder containing `data/`, `metadata/`, `toolkit/`), otherwise commands like `scenarios` print nothing.

```powershell
cd "Briefs\TRUSTED_PETS_PROVING_GROUND_2026 (1)\TRUSTED_PETS_PROVING_GROUND_2026"
python examples\quickstart.py                      # protects health/ed_visits for HEALTH-S1, writes a scorecard
pets-eval scenarios                                # 27 sharing scenarios
pets-eval tasks --dataset health                   # utility tasks for a dataset
pets-eval scorecard --original data/health --protected <out>/health --scenario HEALTH-S1
pets-eval detect --pred <labels.csv>               # score column-role detection
pets-eval text --gold <spans.jsonl> --pred <spans.jsonl>
pets-eval check <folder>                           # leftover direct identifiers
```

Read every CSV with `dtype=str`: phone numbers, postcodes and IDs break when parsed as numbers.

## Verified on the first machine (6 Nov)

- `pets-eval` 1.0.0 installed; the package's 21 tests pass (about 7 minutes; the scorer is slow on large tables).
- The quickstart ran: privacy 0.37, utility 0.79, composite 0.49 on HEALTH-S1. The weak spot is k<5 (0.99 of rows); linkage re-identification dropped from 18.5% / 54% / 57% to 5.5% / 2% / 0% across the three attackers.

## Repo hygiene (do before the first commit)

`.gitignore` must cover at least:

```gitignore
.venv/
# ~1 GB package incl. truth/ (who is who) and the raw data
Briefs/
# scoring only, never publish
rowmap_*.csv
truth/
# only if it contains rowmaps; decide when we create it
pets_submission/
# HMAC key, LLM API keys
.env
```

- The HMAC pseudonym key comes from an environment variable, never from code.
- The source zip for submission must exclude data files and dependencies (limit 100 MB).
- The repo is private. If it's ever made public, check the history for data and rowmaps first.
