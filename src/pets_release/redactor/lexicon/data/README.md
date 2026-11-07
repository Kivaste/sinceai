# Lexicon CSVs (editable)

Pinned columns, in this order: `term,lang,label,match,boundary,notes`. UTF-8; a BOM from Excel is fine.
Edit a file, restart the process (the loader caches per directory). A bad header, an empty term or an
unknown `match` kind is refused with the file and line.

**General-knowledge terms only.** Nothing here may come from the kit's rows. The controller gazetteer
(customer names, cities, streets, per-conversation customer/agent) is built at runtime from the source
tables and is never written to disk.

| file | label | `match` kinds read |
|---|---|---|
| `names_given.csv`, `names_family.csv` | PERSON | `lemma` (dictionary form; case endings and consonant gradation are matched) |
| `cues.csv` | PERSON | `cue-strong` (an unknown capitalised word after it is a name), `cue-weak` (only known names count after it). Cues are never part of the span. |
| `denylist.csv` | PERSON (and shared) | `deny`: common words never taken as names when lower-case or sentence-initial; rows whose notes start with `controller` (Aallokko, the bot Aava) are never labelled in any label |
| `places.csv` | LOCATION | `lemma` (notes `municipality` = minor place, read as a name when it is also a name), `cue-strong` (unknown capitalised word with a place ending after it) |
| `streets.csv` | ADDRESS | `street` (ending of a street name: katu, tie, ...), `apartment-marker` |
| `orgs.csv` | ORG | `phrase` (known organisations), `legal-suffix` (Oy, Ltd, ...), `cue-strong` (employer / operator / bank cues; boundary `multi` = needs two or more words) |
| `dates.csv` | DATE | `month`, `month-stem`, `month-abbr` |
| `health.csv` | HEALTH | `prefix` (word-initial health stems), `cue` (clause starter kept inside the span), `stopword` (connective that never opens a span) |
| `boundaries.csv` | all | `rule` rows: `term` starts with `@`, the `boundary` column holds the value |

## Boundary rules (`boundaries.csv`)

| rule | label | values | meaning |
|---|---|---|---|
| `@case_ending` | PERSON, LOCATION, ORG, ADDRESS | `include` / `exclude` | case ending is inside the span (Virtasen) or cut off |
| `@postcode_town` | ADDRESS | `absorb` | contiguous postcode and town belong to the ADDRESS span |
| `@date_trailing_dot` | DATE | `include` / `exclude` | the dot of `15.3.` |
| `@health_left`, `@health_right` | HEALTH | integer | words of the clause taken left / right of the health term |
| `@person_merge` | PERSON | `merge` / `split` | adjacent name words are one span or one each |
| `@person_lowercase` | PERSON | `cue` / `gazetteer` / `party` / `known` | which lower-case (ASR) names count |
| `@person_gz_capitalised` | PERSON | `any` / `party` | capitalised names known only from the gazetteer |
| `@org_lower_run` | ORG | integer | longest lower-case organisation name after a cue |

Fixed by the span guidelines and not switchable: the cue word is never in the span; AGE is the number only;
a HEALTH span is the phrase, never the whole turn.
