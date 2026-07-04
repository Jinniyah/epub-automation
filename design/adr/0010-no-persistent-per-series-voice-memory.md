# ADR-0010: No persistent per-series/per-author voice memory; session-local exception only

## Status
Accepted

## Context
A book's TTS voice is chosen per book, after metadata resolution
(voice selection can't happen earlier — see `requirements/02-pipeline-
stages.md` §Stage 3). A natural convenience feature would be remembering
"the mother always uses voice X for series Y" persistently across
sessions. This was considered and initially deferred as unnecessary
complexity; on reflection during review it was worth a second look
specifically because it was decided somewhat late in the original design
process.

## Decision
Keep the simplification: `settings.json`'s `last_voice` is a single
**global** suggestion (updated on every voice selection, for any book),
not tracked per-series or per-author. Add one narrow, session-local
enhancement rather than reopening full per-series memory: **within a
single multi-book batch**, if two or more books share a series, those
specific rows in the voice-assignment table default to the same voice as
each other (computed fresh from that batch only). This is never
persisted to `settings.json` or any other store, and is forgotten the
moment the batch ends.

The audit log's `voice` column remains the fallback mechanism for
answering "what voice did I use for this series last time" across
sessions, surfaced to the mother through the plain-language, read-only
"What voice did I use before?" screen
(`requirements/03-gui-ux-design.md` §Settings areas) — she never opens
the raw log.

## Consequences
- Solves the single most likely real annoyance (wanting voice
  consistency across a series she happens to be converting in the same
  sitting) without reintroducing the cross-session per-series/per-author
  complexity that was explicitly rejected — no new persisted data
  structure, no invalidation/edge-case logic for series that later gets
  a different voice on purpose.
- She remains fully free to give different books different voices
  afterward — the session-local default is a starting point, not a
  lock; "Change Voice" always overrides it per row.
- The audit log becomes load-bearing as the actual cross-session memory
  mechanism, which is why its read-failure modes are treated seriously
  (`requirements/06-safety-error-handling.md` §Error communication:
  audit log read failures must degrade gracefully, never crash the
  lookup screen).
- This remains a decision "worth a second look on reflection"
  (`requirements/08-open-questions-and-assumptions.md`) — flagged, not
  fully closed, though the review pass reaffirmed the general
  simplification.

## Alternatives Considered
- **Full per-series/per-author persistent voice memory** — rejected:
  adds real edge cases (what happens when she deliberately wants a
  different voice for a series next time? per-author when an author
  writes across genres?) for marginal benefit over the audit-log-lookup
  fallback that already exists for the rare case she wants to check.
- **No session-local exception either — pure global default, always**
  — rejected: this was the original design, but review surfaced that
  a same-sitting multi-book batch spanning one series (the Alex Verus /
  Wheel of Time example in `03-gui-ux-design.md`) is common enough that
  defaulting the whole table to one global voice, forcing her to
  manually re-pick the same voice for each book in a series she's
  converting together, is an avoidable bit of repeated work for a
  persona where "fewer decisions per screen" is a stated priority.

## References
- `requirements/03-gui-ux-design.md` §Voice assignment
- `requirements/05-data-settings-and-logging.md` §Settings schema
  (`last_voice`)
- `requirements/08-open-questions-and-assumptions.md` (per-series voice
  memory item)
