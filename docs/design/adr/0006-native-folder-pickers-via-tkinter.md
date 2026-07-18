# ADR-0006: Native OS folder pickers via `tkinter.filedialog`, called from Flask

## Status
Accepted

## Context
The GUI is a browser page (ADR-0001), and needs to let the mother pick
her books folder and output folder once during first-run setup (and
later via "Change my folders"). Browsers cannot open native OS
file/folder picker dialogs or read arbitrary filesystem paths directly —
this is a deliberate browser sandboxing restriction, not a gap to work
around with a web-based file input, which would only expose
already-known files rather than letting her browse the filesystem.

## Decision
The Flask backend (which runs natively on her machine, unsandboxed) uses
`backend/dialogs.py` to pop a real native folder-picker dialog via
`tkinter.filedialog`, and hands the chosen path back to the React page
over the JSON API. The browser page never needs filesystem access
itself.

## Consequences
- Preserves the "pick once, remembered forever" UX
  (`docs/requirements/03-gui-ux-design.md` §First launch only: one-time
  setup) without the web page needing any filesystem permissions.
- Introduces `tkinter` as a dependency — but this is a zero-cost
  addition, since `tkinter` is already part of the Python standard
  library and is separately needed for the browser-launch-failure
  fallback dialog (`docs/requirements/07-packaging-deployment.md`
  §Browser-launch fallback), so no new dependency is introduced by this
  decision in practice.
- The native dialog appearing while a browser page is open is an
  intentional, accepted bit of platform-crossing UI — the tradeoff is
  judged worth it against the alternative (a web-based `<input
  type="file">` that can't browse folders or remember a starting
  location the way a native dialog can).
- This only works because the Flask process runs on the same machine as
  the user, unsandboxed (ADR-0008's localhost-only architecture) — this
  pattern would not be available if the GUI were ever made networked/
  multi-device, which is one more reason that remains explicitly out of
  scope without a new design pass.

### Addendum (2026-07-18): tkinter needs one consistent thread, not "the Flask request thread"

**Real bug found via live testing, not a design-time concern** (see
`docs/BACKLOG.md` Epic 10 Phase A). This decision's original Context/
Consequences didn't account for a real constraint: every Flask route
runs on one of `waitress`'s worker-thread pool threads (a fresh one from
a rotating pool of 4 on each request, `01-architecture.md` §Tech stack
summary) — never the process's actual main thread. Tcl/Tk's global
interpreter state isn't safe to touch from a *different* thread on every
call, and calling `tkinter.filedialog.askdirectory()` directly from a
route handler intermittently hangs *forever* — reproduced live by
calling `POST /api/dialogs/folder` against a real running server and
watching the request never return, while every other route kept
responding normally (proof that exactly one of `waitress`'s *finite*
worker threads got stuck, not that the whole server broke — though
enough unlucky clicks would eventually exhaust all of them and take the
whole app down).

**Fix**: `backend/dialogs.py::request_folder_pick()` — a persistent,
lazily-started background thread, created once and reused for the
process's whole lifetime, that owns every real `tkinter` call from then
on. A Flask route (or anything else) submits a request to it via a
queue and blocks waiting for the answer, which is exactly the behavior
already needed (the request is *supposed* to block until she answers
the dialog) — the only change is *which* thread ends up doing the
actual `tkinter` work. `pick_folder()` itself (the plain, directly
testable dialog logic with injectable `tk_factory`/`ask_directory`
seams) is unchanged; `request_folder_pick()` is a thin wrapper around
it, and is what `backend/app.py::pick_folder_route()` actually calls.
Live-verified (not just unit-tested) against a real running server with
both sequential and concurrent load, fixed and stable — see
`docs/BACKLOG.md` Epic 10 Phase A for the exact checks run.

A subprocess-per-dialog-call was considered and rejected: it also would
have sidestepped the threading issue, but doesn't survive being frozen
into a single PyInstaller `.exe` the way this app ships (Epic 10 Phase
B) — `sys.executable` inside a frozen build points at the exe itself,
so re-invoking it as a subprocess would try to launch a second full
instance of the app rather than a lightweight dialog helper.

## Alternatives Considered
- **HTML `<input type="file" webkitdirectory>`** — rejected: browser
  file inputs can select files/folders the browser is shown, but can't
  open an arbitrary native OS dialog with a remembered starting
  location, and reading back a full absolute path from a browser file
  input is unreliable/restricted for security reasons across browsers.
- **A custom in-page folder browser (list directories via an API call)**
  — rejected: reinvents a native OS capability, is more code to build
  and make accessible (per the RA/FMS persona constraints), and offers
  no advantage over just using the real OS picker the backend can
  already summon.

## References
- `docs/requirements/01-architecture.md` §Why these specific technology
  choices (native folder dialogs bullet)
- `docs/requirements/03-gui-ux-design.md` §First launch only: one-time
  setup
