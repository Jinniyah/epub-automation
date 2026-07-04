# ADR-0007: Single-instance lock shared by both CLI and GUI front doors

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

## Decision
A lock file, checked at launch and acquired identically by `main.py` and
`launcher.py` — the same mechanism regardless of which front door is
starting. If the GUI is already running and she double-clicks the
shortcut again, the second launch just opens a new browser tab to the
existing server rather than starting a second instance. If the CLI is
invoked while the GUI (or another CLI run) already holds the lock, it
fails fast with a clear message rather than queuing, blocking silently,
or proceeding anyway.

## Consequences
- Protects the state file/audit log from concurrent-write corruption
  and prevents the specific resource-contention scenario of her GUI
  mid-audiobook while a CLI `audio` run starts on the same machine.
- The lock check must be identical for both front doors — a
  CLI-only or GUI-only lock would leave the other combination
  unprotected, defeating the purpose.
- A double-click on an already-running GUI is handled gracefully (new
  tab, not an error) — this matters for the mother's persona
  specifically, since "I don't remember if I already started this" is a
  very plausible scenario for someone who has difficulty holding
  multi-step processes in mind.
- The CLI failing fast with a clear message (rather than silently
  queuing) is a deliberate choice for the technical front door — a
  technical user benefits more from an immediate, actionable error than
  from a queued run they might not realize is waiting.

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

## References
- `requirements/01-architecture.md` §Single-instance behavior
- `requirements/06-safety-error-handling.md` §Long-run resilience
