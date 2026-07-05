# ADR-0005: Settings/state/audit data lives under `%APPDATA%`, written atomically, with a versioned schema

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

A third problem, surfaced during the pre-code design review and folded
into this same ADR rather than a separate one (they're the same
underlying concern — "can this file always be read safely by the app
that needs it"): neither `settings.json` nor the state file had any
marker distinguishing an old-but-valid file (from a prior app version)
from a genuinely corrupted one. Since `settings.json` is explicitly
designed to survive app updates (see Decision below), and this project's
own reuse/portfolio framing all but guarantees its shape will need to
change at least once, that ambiguity would eventually become a real
problem, not just a theoretical one.

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

**Both files also carry a `schema_version` integer field** (starting at
`1`), written on every save. Policy on version mismatch: an older
version than the running app expects is migrated forward (each future
schema change ships its own explicit migration step); a newer version
than the running app expects (e.g. a downgrade) is treated the same as
an unparseable/corrupted file, rather than guessed at; a file with no
version field at all is treated as version `1` if it otherwise parses
and matches that shape (forward-compatible with any real install that
predates this field), and as corrupted otherwise.

## Consequences
- Settings/state survive app updates: shipping a new `.exe` to an
  existing install never overwrites saved folders, toggles, last-used
  voice, or a customized profanity list.
- Both front doors (CLI and GUI) share the same config path with no
  separate paths to keep in sync — one source of truth
  (`docs/requirements/05-data-settings-and-logging.md`).
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
- **The schema-version addition means a genuine future schema change is
  a planned, migratable event instead of an ambiguous one.** Without it,
  a future version bump would either have to guess whether an old file
  is "valid-but-old" or "corrupt," or would need this same fix added
  retroactively after real installs already have unversioned files on
  disk — meaningfully harder than adding one field now, before any real
  install exists.

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
- **No schema version field; treat any unparseable or unexpected-shape
  file as corrupted and fall back to the existing corruption-recovery
  path** — rejected: conflates two different situations (a deliberate
  future format change vs. accidental corruption) that call for
  different handling — a migratable old file shouldn't be discarded the
  same way a genuinely broken one is. Adding one field now is cheap;
  reconstructing this distinction later, once unversioned files already
  exist on real installs, is not.

## References
- `docs/requirements/05-data-settings-and-logging.md` (full, especially
  §Where settings live, §Schema versioning, and §Write safety)
- `docs/requirements/07-packaging-deployment.md` §Known packaging
  constraints, §Uninstalling
