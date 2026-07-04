# ADR-0005: Settings/state/audit data lives under `%APPDATA%`, written atomically

## Status
Accepted

## Context
The application needs to persist settings (folders, toggles, AI key,
voice preference, profanity list), a resume state file, an audit log,
cached voice samples, and internal working copies of books being
processed (`Library/`). The shipped artifact is a single PyInstaller
`.exe`, potentially installed somewhere access-restricted
(Program-Files-style), and must survive being replaced by a future
version of the `.exe` without losing any of this.

A related, independently-motivated problem: none of these files can
tolerate being left in a partially-written state if the process dies
mid-write (power loss, forced restart, AV lock, crash) — a truncated or
half-old/half-new `settings.json` would either crash the app on launch
or silently reset the mother's install to a blank first-run state, with
no explanation, for a persona for whom redoing unfamiliar multi-step
setup is a real cost.

## Decision
Everything the app stores locally lives under one location,
`%APPDATA%\EpubAutomation\` — settings, state file, audit log, sanitize
sidecar reports, cached voice samples, and the internal `Library/`
working folders — rather than inside the install directory or scattered
across OS-specific cache paths.

`settings.json` and the state file are both written using a
write-to-temp-then-atomic-rename pattern
(`os.replace()` on Windows) — never opened and overwritten in place.
This is a hard requirement, not a style preference.

## Consequences
- Settings/state survive app updates: shipping a new `.exe` to an
  existing install never overwrites saved folders, toggles, last-used
  voice, or a customized profanity list.
- Both front doors (CLI and GUI) share the same config path with no
  separate paths to keep in sync — one source of truth
  (`requirements/05-data-settings-and-logging.md`).
- A crash or forced kill mid-write can never leave `settings.json` or
  the state file in an unparseable, half-written state — the rename
  either fully happens or fully doesn't.
- The install directory itself can be fully read-only/access-restricted
  without breaking anything, since nothing writable lives there.
- Uninstalling is two manual deletions (the `.exe`/shortcut, and
  `%APPDATA%\EpubAutomation\`) with nothing left behind and no
  uninstaller script needed for v1.
- New-machine migration is explicitly out of scope: nothing copies
  `%APPDATA%\EpubAutomation\` between machines. A fresh install plus
  re-pointing "Change my folders" is the supported path — a deliberate
  choice not to build a migration feature nobody asked for.
- This pattern is applied narrowly (settings.json, state file) rather
  than to every file the app touches — e.g., the sanitize stage's
  temp-directory-then-cleanup workflow (ADR-0004) is a related but
  separate mechanism for a different kind of atomicity (whole-operation
  rollback vs. single-file write safety).

## Alternatives Considered
- **Store settings alongside the `.exe`'s install location** —
  rejected: not reliably writable if installed in a restricted location,
  and would be at risk of being wiped or orphaned by a future app
  update/reinstall.
- **Direct in-place writes (`open(path, "w")`)** — rejected: not
  atomic; an interrupted write can leave invalid JSON with no recovery
  path, which is an unacceptable failure mode given what
  `settings.json` alone holds for this persona (see Context).
- **OS-standard cache directories for voice samples specifically**
  (rather than under the same `%APPDATA%\EpubAutomation\` tree) —
  rejected: would scatter what the app has stored across multiple
  OS-specific locations for no benefit, working against "one findable
  place" for everything the app owns.

## References
- `requirements/05-data-settings-and-logging.md` (full, especially
  §Where settings live and §Write safety)
- `requirements/07-packaging-deployment.md` §Known packaging constraints,
  §Uninstalling
