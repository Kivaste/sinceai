Automatic message from `scripts/overnight/gpt-quota-probe.ps1`: **the GPT-6.1 Sol quota has reset** (a probe just succeeded; the time is in `.scratch/local-overnight/gpt-available.json`). This applies D13d. Switch now:

1. **Core tickets (`model:opus`):** the second reviewer goes back to `openai/gpt-6.1-sol#high` in place of `opencode-go/gpt-6-luna`, for every new review from now on. Grok stays the first reviewer.
2. **Numbers code (18, 19, 22, 25, 29):** the second reviewer is `openai/gpt-6.1-sol#high`.
3. **Retroactive GPT-6.1 Sol review (read-only) of core tickets whose second review was Luna-only:** 05 (gate text checks), 11 (producer-scope checks) and 02's final delta. Luna returned "no findings" on these. Findings that affect fail-closed behaviour, assertions or leaks become must-fix follow-ups.
4. **Final whole-branch review:** `openai/gpt-6.1-sol#high` + `opencode-go/gemini-4-argon#medium`, plus the AGENTS.md rule audit.
5. **Spend the quota carefully:** use GPT-6.1 Sol only for the items above (not routine tickets), with at most 4 concurrent Sol sessions. If it returns a usage-limit error again, fall straight back to Luna and log it.
6. Log the switch in `docs/decision-log.md` (D13d) and write a heartbeat.
