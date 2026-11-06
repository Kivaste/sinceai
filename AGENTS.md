# AGENTS.md

**sinceai** — purpose-first PETs tool for the TrustED PETs Transformer challenge, Since AI Hackathon 2026.
**Deadline: Sun 8 Nov 10:00 EET.**

See `README.md` and `docs/` for the plan, spec and setup.

## Hard rules

- **Never commit** anything from `Briefs/` (the challenge kit), any `rowmap_*.csv`, anything under a `truth/` directory, or secrets (`.env`, HMAC keys, other key material). These are gitignored; don't force-add them.
- **Read every CSV with `dtype=str`** (e.g. `pd.read_csv(path, dtype=str)`). Never let pandas infer types — it mangles IDs, leading zeros and dates.
- **Run `pets-eval` with `PYTHONUTF8=1`** and `--root` pointing at the kit (`Briefs/TRUSTED_PETS_PROVING_GROUND_2026 (1)/TRUSTED_PETS_PROVING_GROUND_2026`).
- **Never send data values to any LLM or network service.** Schema/field names and aggregate metrics only; row values stay local.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `Kivaste/sinceai`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` plus `docs/adr/`. See `docs/agents/domain.md`.
