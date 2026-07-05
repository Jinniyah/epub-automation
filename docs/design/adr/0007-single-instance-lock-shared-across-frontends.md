# ADR-0007: Single-instance lock shared by both CLI and GUI front doors, with stale-lock detection

## Status
Accepted

## Context
Two front doors (`main.py` CLI, `launcher.py` GUI) call into the same
pipeline engine and share the same state file and audit log
(`%APPDATA%\EpubAutomation\`, ADR-0005). Two concerns arise if more than
one instance runs simultaneously **on the same machine**:

1. **State-file integrity** — concurrent writes to the shared state
   file/audit log from two running instances risk corruption or lost
   updates.
2. **Resource contention** — Kokoro's memory footprint during TTS
   inference is large enough that two simultaneous inference jobs on
   typical hardware is a real problem on its own, even if the state
   file were made perfectly concurrency-safe. This isn't just a
   data-integrity issue to guard against — it's a performance/stability
   problem to prevent outright.

Scope note: each family member runs their own separate install on their
own machine (own `%APPDATA%`, own `Library/`, own settings/audit log) —
there is no shared/networked instance across the family (consistent with
ADR-0008's localhost-only binding). "Single instance" therefore means
*per machine*, not one instance for the whole family.

**A third concern, surfaced during the pre-code design review:** a lock
file with no liveness check is a real risk given the failure modes this
project explicitly designs around elsewhere — `06-safety-error-handling.md`
§Long-run resilience treats a crash, a forced restart, or a lost-power
event during a multi-hour audio job as *expected*, not exceptional. Every
one of those scenarios would leave a naive "does the lock file exist"
check permanently refusing to start the app on the next launch, with no
visible recovery step for a persona this project is specifically built to
let use the app unassisted.

## Decision
A lock file, checked at launch and acquired identically by `main.py` and
`launcher.py` — the same mechanism regardless of which front door is
starting. If the GUI is already running and she double-clicks the
shortcut again, the second launch just opens a new browser tab to the
existing server rather than starting a second instance. If the CLI is
invoked while the GUI (or another CLI run) already holds the lock, it
fails fast with a clear message rather than queuing, blocking silently,
or proceeding anyway.

**The lock file records enough information to check whether its holder
is actually still running, not just whether the file exists:** the
holding process's PID (and ideally its image name, to guard against PID
reuse after a reboot). On launch, if a lock file is present, a new
process checks whether that PID (and image name, if recorded) is
actually alive before treating the lock as held. If it isn't, the lock is
treated as abandoned — cleared automatically, logged, and the launch
proceeds normally. This check is identical for both front doors, the
same as acquisition itself.

## Consequences
- Protects the state file/audit log from concurrent-write corruption
  and prevents the specific resource-contention scenario of her GUI
  mid-audiobook while a CLI `audio` run starts on the same machine.
- The lock check must be identical for both front doors — a
  CLI-only or GUI-only lock (or stale-lock check) would leave the other
  combination unprotected, defeating the purpose.
- A double-click on an already-running GUI is handled gracefully (new
  tab, not an error) — this matters for the mother's persona
  specifically, since "I don't remember if I already started this" is a
  very plausible scenario for someone who has difficulty holding
  multi-step processes in mind.
- The CLI failing fast with a clear message (rather than silently
  queuing) is a deliberate choice for the technical front door — a
  technical user benefits more from an immediate, actionable error than
  from a queued run they might not realize is waiting.
- **The stale-lock check closes a real gap the original decision left
  open:** without it, every crash/forced-restart/lost-power scenario
  this project already designs around elsewhere would permanently lock
  the mother out of her own app after exactly the kind of interruption
  the rest of the design treats as routine — directly undermining the
  "usable unassisted" premise the whole GUI exists to satisfy. This is a
  liveness check only, not a recovery mechanism — actual recovery of
  in-progress work remains the state-file-driven "Welcome back" flow
  (`06-safety-error-handling.md` §Long-run resilience), which is
  unaffected by this addition.

## Alternatives Considered
- **Separate locks per front door** — rejected: doesn't address the
  Kokoro memory-contention problem, which cares about *any* two
  simultaneous runs on the machine, not just two of the same front
  door.
- **No lock; rely on the state file being concurrency-safe** —
  rejected: even a perfectly safe state file doesn't solve the memory-
  contention problem, which exists independent of data integrity.
- **Queue a second invocation rather than reject it** — rejected for the
  CLI: silent queuing without clear feedback is worse for a technical
  user than an immediate, explicit failure they can act on.
- **A lock file with no liveness check (the original decision, before
  this review)** — rejected on review: correct for the concurrent-write
  and resource-contention problems it was designed for, but silent about
  what happens when the process holding it dies without releasing it —
  precisely the scenario this project's own long-run-resilience design
  treats as routine. Leaving this unresolved would have meant the fix
  for "an interrupted audio job is safe to resume" (the state file) and
  the mechanism that could prevent her from ever reaching that resume
  screen (an orphaned lock) coexisting without either one accounting for
  the other.
- **A time-based staleness threshold instead of a PID-liveness check**
  (treat any lock older than N hours as abandoned) — considered as a
  simpler alternative, but rejected: an audio job can legitimately run
  for many hours, so a fixed threshold either has to be set uncomfortably
  long (delaying real recovery from a genuine stale lock) or risks
  incorrectly clearing the lock out from under a real, still-running,
  simply-long job. A PID-liveness check doesn't have this tradeoff.

## References
- `docs/requirements/01-architecture.md` §Single-instance behavior
- `docs/requirements/06-safety-error-handling.md` §Long-run resilience
- `docs/requirements/09-testing-strategy.md` §Priority coverage areas
  (stale-lock regression test)
