# Concept: purpose-first data release

Status: **decided** (direction). Terms are defined in [GLOSSARY.md](../GLOSSARY.md).

## The idea in one line

The tool takes a **data request** ("I'm a researcher studying ED revisits"), works out which fields are needed and at what detail ("arrival week, not minute; age band, not birth date"), **withholds** everything else, and only then transforms and verifies. Its output is a **release** plus a **field justification** for every field.

## Why this angle

- **The obvious answer starts from the data**: detect column types → apply the matching PET → score. Most AI-assisted teams will build that. We start from the **business need**: who receives the data, why, and in what form.
- **It's what the law asks for.** GDPR purpose limitation and data minimisation (Art. 5(1)(b)–(c)): collect and share only what's necessary for a stated purpose. The TrustED evaluators will recognise this framing.
- **The scorer rewards it.** k-anonymity risk is computed only on the quasi-identifiers *kept*, and an unreleased table is reported as "withheld", not as a failure. The quickstart kept fields its scenario didn't need, which is part of why 99% of its rows had k<5.
- **The brief allows it.** "Transformed dataset *or protected view*": the right release is sometimes a few aggregate tables, not rows.
- **It gives the business story** for the builder vote, which is decided on a tagline and a 2-minute video.

## What makes it more than a config file

1. **Plain-language request in, measurable needs out.** Real data requesters never arrive with test cases. The tool turns a request into a **needs spec** *and* into **purpose checks** (executable analyses), so "still useful" becomes measurable for any request.
2. **The minimum is measured, not asserted.** For each needed field, a search walks down its **detail ladder** and keeps the coarsest level at which every purpose check still passes.
3. **Every decision explains itself.** The search log becomes the field justifications and the privacy/utility trade-off chart.
4. **Verified by an attacker the optimiser never saw** (see [evaluation-strategy.md](evaluation-strategy.md)).

## Prior art to acknowledge

Generalisation-search tools such as ARX already find good generalisation levels for k-anonymity. Our novelty is the **purpose layer** in front of the search (request → needs → purpose checks) and the **explanation** after it. The search itself can stay simple.

## Demo story (draft)

1. Type a data request.
2. The tool shows its needs spec: each field, its level of detail and why; the rest withheld.
3. It produces the release and shows the release form it chose and why.
4. Before vs after: attacker success, risk components, purpose-check results.
5. "Fit for: controlled research. Not fit for: public release, because …" (honest residual risks).
