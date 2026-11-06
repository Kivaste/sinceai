---
status: accepted
---

# Row maps live only in a separate private repo

`pets_submission/`, including row maps, is not this repository's problem to store. A private branch here would not stay private.

## Context

`pets-eval` row maps link released rows back to source rows. The organiser check needs them. This repo must never contain them (AGENTS.md; `rowmap_*.csv` is gitignored), and the repo goes public at submission (D1). History was already rewritten once, on Fri 23:53, to remove the challenge kit. That is not a procedure we should need again on Sunday morning.

## Decision

`pets_submission/` including row maps lives only in the separate private repo `Suhtetark-Kool/trusted-since-ai`, with the organisers invited. The public repo never contains row maps. Confirm the delivery method with TrustED on Discord Saturday morning. See D15.

## Alternatives considered

- **Private branch in `Kivaste/sinceai`, deleted before the repo goes public.** Rejected. GitHub keeps commits reachable by SHA after the branch is deleted. Anyone who has the SHA — a fork, a clone, an actions log, a shared link — can still fetch the commit once the repository is public. Deleting the branch does not delete the objects.
- **Gitignore the maps here and hand them over out of band.** Rejected as the storage plan. A force-add or a worktree slip puts them in this history, and this history is about to become public. A second repo cannot be published by making this one public.
- **Keep all of `Kivaste/sinceai` private.** Rejected. Submission requires the repo to go public.

## Consequences

Release tooling must not write row maps into this tree as tracked files. The copy that the organisers receive is produced in `Suhtetark-Kool/trusted-since-ai`. How TrustED wants that handoff (invite, upload, or something else) is still to be confirmed on Discord; that confirmation does not change where the files live.
