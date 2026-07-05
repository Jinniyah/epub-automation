# Architecture Decision Records — epub-automation

Each ADR captures one binding decision, the alternatives considered, and
the consequences accepted. Source detail for every ADR lives in the
`docs/requirements/` docs cited within it — these ADRs are a distilled,
decision-focused view, not a replacement.

Status legend: **Accepted** (decided, ready to build against) ·
**Proposed** (not yet confirmed — see linked open item) ·
**Superseded** (replaced by a later ADR, kept for history)

| # | Title | Status |
|---|---|---|
| [0001](0001-flask-waitress-react-over-pywebview.md) | GUI transport & process model: Flask/waitress + React, not pywebview | Accepted |
| [0002](0002-local-kokoro-tts-over-browser-automation.md) | Local Kokoro TTS engine, not browser-automation (Perchance/Selenium) | Accepted |
| [0003](0003-pluggable-user-keyed-ai-provider.md) | Pluggable, user-selected, user-keyed AI metadata provider | Accepted |
| [0004](0004-sanitize-ported-powershell-to-python.md) | Port sanitize stage from PowerShell to Python, preserving all security controls | Accepted |
| [0005](0005-appdata-settings-storage-atomic-writes.md) | Settings/state/audit data lives under `%APPDATA%`, written atomically, with a versioned schema | Accepted |
| [0006](0006-native-folder-pickers-via-tkinter.md) | Native OS folder pickers via `tkinter.filedialog`, called from Flask | Accepted |
| [0007](0007-single-instance-lock-shared-across-frontends.md) | Single-instance lock shared by both CLI and GUI front doors, with stale-lock detection | Accepted |
| [0008](0008-localhost-only-binding.md) | Flask/waitress binds to `127.0.0.1` only — hard requirement, not a default | Accepted |
| [0009](0009-serial-audio-generation-reserved-workers-flag.md) | Audio generation is serial (one book at a time); CLI reserves a `--workers` flag for future use | Accepted |
| [0010](0010-no-persistent-per-series-voice-memory.md) | No persistent per-series/per-author voice memory; session-local exception only | Accepted |
| [0011](0011-pyinstaller-packaging-no-code-signing.md) | PyInstaller single `.exe`, no code signing purchased | Accepted |
| [0012](0012-retain-copyleft-dependencies.md) | Retain `mutagen` (GPL) and `ebooklib` (AGPL) rather than replace them | Accepted |
| [0013](0013-epub-only-input-format.md) | Accept `.epub` input only; validate content, not extension | Accepted |
| [0014](0014-reuse-existing-implementations-by-default.md) | Reuse existing implementations by default; write new code only where there's a concrete reason | Accepted |
| [0015](0015-wcag-aa-alignment-broadened-accessibility-scope.md) | Broaden accessibility scope to WCAG 2.1 AA alignment (screen readers, dyslexia), layered on top of the original persona | Accepted |
| [0016](0016-windows-safe-filesystem-naming.md) | Windows-safe filesystem naming (illegal characters, reserved device names) and long-path handling | Accepted |
| [0017](0017-library-staging-cleanup.md) | Automatic cleanup of internal `Library/` staging copies after a book completes | Accepted |

## Post-review fixes (2026-07-05 design-review pass)

A final pre-coding design review surfaced three gaps cheap to fix now and
expensive to retrofit after real installs exist, folded into the
relevant existing ADRs above rather than given new numbers, since each
one refines an already-accepted decision rather than introducing a new
one:

- **ADR-0005** — added `schema_version` to `settings.json` and the state
  file, plus the policy for what a version mismatch means.
- **ADR-0007** — added PID-based stale-lock detection, so a crash/forced-
  restart/lost-power event (already treated as routine elsewhere in this
  design) can't leave the app permanently refusing to start.
- **ADR-0004** — flagged that the sanitize stage's whole-word-matching
  regex and its ReDoS timeout need a real dependency decision in the
  Python port (Python stdlib `re` can't reproduce either), found by
  reading the actual PowerShell source directly.

A fourth item — an explicit `state` derivation rule for the GUI/backend
polling contract, and aligning its `voice_pick`/`voice_pending`
vocabulary — was added directly to `docs/requirements/01-architecture.md`
§Status endpoint contract, since that contract isn't itself the subject
of a dedicated ADR.

See `docs/design_review.md` for the full review this pass responds to.

## Post-backlog-kickoff additions (2026-07-05)

A follow-up "what's this project still missing" pass, done after the
backlog was already sequenced, surfaced two more gaps significant enough
to warrant their own ADRs rather than folding into an existing one —
neither had a natural existing home:

- **ADR-0016** — Windows-illegal filename characters and path-length
  limits, found to be entirely unaddressed despite every generated
  filename coming from arbitrary real-world book metadata.
- **ADR-0017** — no policy existed for cleaning up the internal
  `Library/` staging copies after a book completes, risking unbounded
  disk growth over the tool's real-world lifetime.

Two further findings from the same pass were **not** turned into ADRs,
because they involve a real tradeoff this project's author should weigh
in on rather than one this review should decide unilaterally — see
`docs/requirements/08-open-questions-and-assumptions.md` for both
(PyInstaller `--onefile` vs. `--onedir` packaging, and whether
per-chunk audio files should be merged into per-chapter files before
calling v1 done).
