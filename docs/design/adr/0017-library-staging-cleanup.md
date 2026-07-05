# ADR-0017: Automatic cleanup of internal Library staging copies after completion

## Status
Accepted

## Context
Found during a post-backlog "what's this project still missing"
review. Per the folder-mapping design (`01-architecture.md` §Folder
mapping), a book's content is copied — never moved — through up to four
internal working locations (`Library/00-Incoming/` →
`01-Renamed/` → `02-Sanitized/` → `03-Audio/`), and *also* copied out to
her `output_folder` as each relevant stage finishes. Nothing in the
design as written ever deletes the internal working copies once a book
is fully done. Over months of real use, that's unbounded growth in
`%APPDATA%\EpubAutomation\Library\` — up to four redundant copies of
every book's content sitting on disk indefinitely, on top of her
original in `books_folder` and the finished output in `output_folder`.
This directly undercuts the disk-space safeguards
(`06-safety-error-handling.md` §Resource & cost safety) that only
account for *this batch's* space needs, not cumulative long-term growth
from every prior batch never being cleaned up.

## Decision
Once a book reaches `complete` status in the state file — meaning every
stage enabled for that run has finished **and** its output has already
been successfully copied to `output_folder` — automatically delete that
book's working copies from every `Library/*` stage folder it passed
through. This runs immediately as part of finishing that book, not on a
delay, not conditional on her taking any action, and not deferred to
app restart.

**Explicit exception:** a book left in `cancelled` status with
keep-partial chosen (`06-safety-error-handling.md` §Cancel design) is
**not** cleaned up — its partial `Library/03-Audio/` chunks are exactly
what makes a future resume possible, and deleting them would silently
convert "kept partial progress" into "actually discarded progress"
without her having chosen that.

This makes `Library/*` explicitly transient working space, never a
second permanent archive — `output_folder` and her own `books_folder`
remain the only two locations she should ever think of as permanent,
consistent with the original copy-not-move design intent.

## Consequences
- Disk usage stays bounded by roughly one batch's worth of working
  copies at a time, not every batch ever run — the existing disk-space
  estimate (`06-safety-error-handling.md`) now actually reflects
  reality over the tool's lifetime, not just its first use.
- Cleanup must be resilient to partial failure itself (e.g. a file
  locked by another process at the moment of cleanup) — a failed
  cleanup attempt should log and move on, never block or fail the batch
  that already succeeded from her point of view.
- The state file needs to distinguish "complete and cleaned up" from
  "complete, cleanup pending/failed" so a later launch can retry
  cleanup for anything missed, rather than leaking space silently
  forever if one cleanup attempt fails.
- No new UI surface is needed — this is invisible to her by design,
  consistent with not asking her to manage anything she didn't
  explicitly create (she never chose to put files in `Library/` in the
  first place, so she shouldn't need to manage removing them either).

## Alternatives Considered
- **Manual "Clean up old files" button** — rejected as the *only*
  mechanism: adds a maintenance task to a persona this whole project is
  built to avoid burdening with maintenance tasks. (A manual button
  could still be added later as a supplementary safety net for a failed
  automatic cleanup, but automatic cleanup is the primary mechanism.)
- **Clean up at next app launch instead of immediately** — rejected:
  delays reclaiming space for no benefit, and risks compounding if she
  runs several batches between rare launches.
- **Never clean up, treat `Library/` as a cache the user manages
  externally** — rejected: this persona was never told `Library/`
  exists, has no OS-level mental model of "clearing app cache," and
  would have no way to discover or act on this even if surfaced.

## References
- `docs/requirements/01-architecture.md` §Folder mapping
- `docs/requirements/06-safety-error-handling.md` §Resource & cost
  safety, §Cancel design
- `docs/requirements/05-data-settings-and-logging.md` §State file
- `docs/BACKLOG.md` Epic 5/Epic 10
