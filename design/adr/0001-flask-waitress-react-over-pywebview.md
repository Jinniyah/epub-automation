# ADR-0001: GUI transport & process model — Flask/waitress + React, not pywebview

## Status
Accepted

## Context
The accessible GUI needs a process model that survives a multi-hour,
unattended audio-generation job. The natural "wrap a local web app in a
desktop window" choice for a Python app is `pywebview`, which embeds a
browser control inside the same process as the application window.

The core risk: if the window and the work are the same process,
closing the window — including by accident, or because the persona this
GUI is built for (FMS: difficulty holding multi-step processes in mind)
might reasonably assume "closing this is fine, I'll come back" — kills
an in-progress job that may have hours left to run.

## Decision
Use a background **Flask API, served via `waitress`** (not Flask's dev
server), with a **React (Vite-built) static frontend**, launched by a
small `launcher.py` that starts the server and opens the default OS
browser to it. The browser tab is a thin client; the server process is
independent of it.

- `waitress` over Flask's built-in dev server: avoids the "do not use in
  production" warning surface and is materially more stable for a
  long-lived, unattended local process.
- React over server-rendered Flask templates: keeps Flask a pure JSON
  API (cleaner separation, see ADR on the polling contract in
  `requirements/01-architecture.md`), and gives a more conventional,
  portfolio-appropriate production architecture.
- A **single-instance lock**, shared with the CLI (ADR-0007), and a
  **localhost-only bind** (ADR-0008), are direct consequences of this
  process model — a real network-facing server process needs both.

## Consequences
- Closing the browser tab/window is always safe — generation continues
  in the background server. This is the entire point of the decision
  and is called out explicitly on the Working screen's copy
  (`requirements/03-gui-ux-design.md` §Screen: Working) so she doesn't
  have to intuit it.
- A **new** failure mode is introduced that pywebview wouldn't have:
  the browser might fail to launch at all (no default browser
  registered, corrupted install). This is mitigated by a documented
  fallback (`requirements/07-packaging-deployment.md` §Browser-launch
  fallback: retry once, then a native `tkinter` dialog with the address
  pre-copied to clipboard).
- Requires an explicit, deliberate "Quit for now" control somewhere
  reachable, since closing the tab no longer stops the background
  process — a UX obligation this decision creates that must not be
  dropped.
- Introduces a genuine second-process lifecycle to manage
  (server up/down, port selection, single-instance) that a pywebview
  app wouldn't need — accepted as the right tradeoff given how long the
  audio stage can run.

## Alternatives Considered
- **pywebview** — rejected: window lifecycle == job lifecycle, which is
  precisely the fragility this decision exists to eliminate.
- **Flask dev server instead of waitress** — rejected: explicitly
  unsupported for anything long-running/production-like; the warning
  banner itself is a signal not to rely on it for a multi-hour
  unattended job.

## References
- `requirements/01-architecture.md` §Tech stack summary, §Why these
  specific technology choices
