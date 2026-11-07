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
`summary.{privacy,utility}`; baseline metrics `utility_mean`, `privacy`, `worst_reid`, `task.<id>`. For
`privacy` and `baselines` the metric (or component) is everything after the 3rd (or 2nd) segment, so it may contain dots.
A null (e.g. B2-k cannot answer H-U6) is rendered `—`.

## Part B: status (filled from the real run)

Release: `C:\Users\kivas\AI\sinceai-out\22\health-s1\` (+ `.scoring`), dashboard `health-s1.dashboard.html/.csv`,
filled kit `C:\Users\kivas\AI\sinceai-out\22\story-kit\` (`numbers.csv`, `pitch-beats.md`, dashboard copies).
Made by `python -m pets_release.measure.wire <run args>` (two passes: scratch release, score it, final release with
`measured.*`), then `docs/story-kit/fill_numbers.py <release> <out_dir>`. `numbers.csv` here is the committed filled
copy; every value is read from a manifest key and agrees with the dashboard CSV. The release is bound to the tool
revision it was built at (see its manifest); docs-only commits after it do not change it.

- `measured.utility.after.*` is the scorecard of the SUPPRESSED release (what the recipient gets). H-U4 is the
  visible loss and is a policy-enumerated sacrifice (`sacrifices.H-U4.floor`).
- Rows vs persons: `k_below_5_share` is the scorecard's share of ROWS (row-weighted over the tables scored for k); `person_k.below_k_share` is OUR
  share of PERSONS. Never mix them up. Per-person k is authoritative (D22: the scorecard is blind to the renamed `age_band`).
- A baseline task the kit publishes as null (B2-k H-U6/H-U7/H-U8) renders `—`: that baseline cannot answer it.

**#52:** the numbers above were produced with the #52 measurer (origin/ticket/fu52-measurer, round 3). If #52 changes
again before it merges, re-fill every `measured.baselines.*` row, every `measured.privacy.before.*` value and the
`person_k.*` rows. `k_below_5_share` is row-weighted over the tables scored for k.

**Residual risks to say out loud:** the D22 scorecard defect (Beat 6); linkage-attackers and attribute-inference rates
are `not_measured` in this release (no attacker run is wired), so no linkage rate is claimed; recipient-mode verify
catches accidents only.

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
