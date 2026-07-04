# ADR-0009: Audio generation is serial (one book at a time); CLI reserves a `--workers` flag for future use

## Status
Accepted

## Context
The audio stage loops over every book in a batch. Running multiple
books' TTS generation in parallel would reduce total wall-clock time for
large batches, but two considerations push against it for the GUI
specifically:

1. **Resource contention** — Kokoro's memory footprint makes concurrent
   inference jobs a real problem on typical hardware, not just a
   theoretical one (the same concern behind ADR-0007's single-instance
   lock).
2. **Progress-reporting simplicity and honesty** — the GUI's polling-
   based status contract (`requirements/01-architecture.md` §Status
   endpoint contract) and Working-screen design assume one active book
   at a time; parallel generation would complicate both the contract and
   the mother-facing progress UI for a benefit (throughput) that matters
   more to technical users than to her.

At the same time, the CLI/advanced front door shouldn't be
architecturally prevented from adding real parallelism later just
because the GUI doesn't need it.

## Decision
Audio generation is **serial only** — one book at a time — in both front
doors, for this version. `main.py`'s `audio` command additionally
accepts a `--workers N` flag, **defaulting to `1`**, as a reserved seam:
it validates and defaults, but does not currently implement parallel
execution. The GUI never exposes this flag and always behaves as if
`--workers 1`.

## Consequences
- The pipeline engine's design does not need to be revisited if real
  parallelism is added to the CLI later — the flag already exists and
  is already wired through validation.
- The GUI's progress-reporting model (one `generating` book at a time in
  the status contract) stays simple and accurate for this version
  regardless of what the CLI eventually does with the flag.
- For large batches (e.g. 15 books) via the GUI, total wall-clock time
  could be very long, since nothing generates concurrently — accepted as
  the right tradeoff for this persona; confirmed acceptable during
  review (`requirements/08-open-questions-and-assumptions.md`).
- If/when real CLI parallelism is implemented, it must respect the same
  single-instance/resource-contention concerns that motivate serial
  generation in the first place (i.e., `--workers N > 1` runs multiple
  jobs within one process/lock, not multiple independent locked
  instances) — this ADR does not resolve that future design, only
  reserves the seam for it.

## Alternatives Considered
- **Implement real parallelism now, for both front doors** — rejected:
  Kokoro's memory footprint makes this a real resource-contention risk
  on typical target hardware, and it would complicate the GUI's
  progress-reporting contract for a persona where simplicity matters
  more than throughput.
- **No reserved flag at all — revisit if/when parallelism is wanted** —
  rejected: adding a `--workers` flag later, after the pipeline engine's
  interface is already settled, is more disruptive than reserving the
  seam now while the engine is still being designed.

## References
- `requirements/01-architecture.md` §CLI: reserved `--workers` flag
- `requirements/02-pipeline-stages.md` §Stage 3 Batch behavior
- `requirements/08-open-questions-and-assumptions.md` (one book at a
  time item)
