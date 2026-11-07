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

The metric ids are the measurer's (`pets_release.measure.ids`): privacy components `k_below_5_share` (row-weighted
share of rows with k<5 over the tables scored for k: released tables reporting a k<5 rate, named in `measured.privacy.source`), `k_below_5_worst_table` (the worst single table, not a row share) and
`linkage_reid` (worst table), baseline metrics `utility_mean` and `worst_reid`. `tests/measure/test_ids.py` checks that this CSV, the
fixture manifest and the measurer agree.

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
