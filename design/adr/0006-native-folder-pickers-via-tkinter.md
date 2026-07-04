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
- Preserves the "pick once, remembered forever" UX (`requirements/03-
  gui-ux-design.md` §First launch only: one-time setup) without the web
  page needing any filesystem permissions.
- Introduces `tkinter` as a dependency — but this is a zero-cost
  addition, since `tkinter` is already part of the Python standard
  library and is separately needed for the browser-launch-failure
  fallback dialog (`requirements/07-packaging-deployment.md` §Browser-
  launch fallback), so no new dependency is introduced by this decision
  in practice.
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
- `requirements/01-architecture.md` §Why these specific technology
  choices (native folder dialogs bullet)
- `requirements/03-gui-ux-design.md` §First launch only: one-time setup
