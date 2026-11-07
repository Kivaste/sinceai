# Story kit (ticket 22)

For the business teammate: a pitch-beat script and a before/after numbers CSV for HEALTH-S1.
Content-free: schema names and aggregate metrics only. No row values anywhere.

- Part A (this folder, now): `pitch-beats.md` and `numbers-template.csv`. Placeholders only, no numbers.
- Part B (blocked on tickets 18, 19, 21): fill the numbers from a real HEALTH-S1 release.

## The rule

Every number in the script traces to a manifest key. A number is written as `{{key.path}}`; the CSV has one
row per placeholder (`beat,label,manifest_key_path,unit,value`). If a key is absent or `not_measured` in the
manifest, the value stays empty and the sentence is dropped. Never type a number by hand.

## Key-path grammar

Paths are dotted. Lists in the manifest are addressed by their id field.

| Path | Resolves to |
|---|---|
| `release.<field>` | `release.<field>` |
| `inventory.count`, `sacrifices.count` | length of the list |
| `fieldJustifications.released.count` / `.withheld.count` | entries with that `decision` |
| `gate.checks.release.count` / `.producer.count` | `gate.checks` entries with that `scope` |
| `exportAssertions.<name>` | the assertion (always `false`) |
| `assertionEvidence.<name>.hits` / `.denominator.n` | evidence record fields |
| `measured.utility.<before\|after>.<task>` | `measured.utility.tasks[task==X].before/after` |
| `measured.privacy.<before\|after>.<component>` | `measured.privacy.components[component==X].before/after` |
| `measured.baselines.<B0\|B2\|B2-k>.<metric>` | `measured.baselines.rows[baseline==X, metric==Y].value` |
| `measured.search.candidates` | search candidate count |

Ids are the measurer's real ones (not the fixture's): privacy components `person_k.{persons,min,below_k_share}`
(ours, after only), `k_below_5_share` (scorecard, ROWS), `linkage_reid`,
`summary.{privacy,utility}`; baseline metrics `utility.HEALTH-S1`, `privacy`, `worst_reid`, `task.<id>`. For
`privacy` and `baselines` the metric (or component) is everything after the 3rd (or 2nd) segment, so it may contain dots.
A null (e.g. B2-k cannot answer H-U6) is rendered `—`.

## Part B: status (filled from the real run)

Release: `C:\Users\kivas\AI\sinceai-out\22\health-s1\` (+ `.scoring`), dashboard `health-s1.dashboard.html/.csv`,
filled kit `C:\Users\kivas\AI\sinceai-out\22\story-kit\`. Made by `python -m pets_release.measure.wire <run args>`
(two passes: scratch release, score it, final release with `measured.*`), then `docs/story-kit/fill_numbers.py`.
`numbers.csv` in this folder is the committed filled copy; it agrees with the dashboard CSV.

**Pending #52 (measurer fixes; re-run both steps when it lands, numbers may change):**
- all `measured.baselines.*` rows (baselines read dataset-wide utility rather than the scenario's; `utility.HEALTH-S1` is the scenario row, but treat the whole block as pending);
- every `measured.privacy.before.*` value (the "before" scoring drops withheld tables);
- `measured.privacy.after.risk.lab_results:*` (not used in the script) and the metric-id mapping above;
- the per-person k rows are produced by the measurer's k summary; the unit (persons) is right, recheck after #52.
Utility before/after (H-U2..H-U8) is not affected as far as known.

**Residual risks to say out loud:** D22 scorecard defect (see Beat 6); linkage-attackers and attribute-inference
rates are `not_measured` in this release (no attacker run wired yet), so no linkage rate is claimed; recipient-mode
verify catches accidents only.

## How part B fills it

1. Produce a real release (ticket 21):
   `pets-release run --scenario HEALTH-S1 --out <R> --created <iso-utc> --kit <K>` (key in `PETS_HMAC_KEY`).
2. Confirm it: `pets-release verify <R>` and `pets-release verify --full --kit <K> <R>`.
3. Render the dashboard: `pets-release dashboard <R> --out <R>.dashboard.html`. Ticket 18 also exports the
   before/after numbers CSV; the story kit's CSV must agree with it.
4. For each row in `numbers-template.csv`, read the key path from `<R>/privacy_manifest.json` using the grammar
   above and write it to `value`. The render step belongs to part B (a small script that reads only the manifest;
   nothing else is read).
5. Substitute the same values into `pitch-beats.md`, and record the release folder and dashboard path as evidence
   in the ticket.

## Test

`tests/story_kit/test_story_kit.py` checks that every placeholder is a CSV row, every CSV row is used and empty,
every key path resolves against ticket 02's schema, and that no percentage is typed in the script.
