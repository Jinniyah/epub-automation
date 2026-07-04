# Architecture Decision Records — epub-automation

Each ADR captures one binding decision, the alternatives considered, and
the consequences accepted. Source detail for every ADR lives in the
`requirements/` docs cited within it — these ADRs are a distilled,
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
| [0005](0005-appdata-settings-storage-atomic-writes.md) | Settings/state/audit data lives under `%APPDATA%`, written atomically | Accepted |
| [0006](0006-native-folder-pickers-via-tkinter.md) | Native OS folder pickers via `tkinter.filedialog`, called from Flask | Accepted |
| [0007](0007-single-instance-lock-shared-across-frontends.md) | Single-instance lock shared by both CLI and GUI front doors | Accepted |
| [0008](0008-localhost-only-binding.md) | Flask/waitress binds to `127.0.0.1` only — hard requirement, not a default | Accepted |
| [0009](0009-serial-audio-generation-reserved-workers-flag.md) | Audio generation is serial (one book at a time); CLI reserves a `--workers` flag for future use | Accepted |
| [0010](0010-no-persistent-per-series-voice-memory.md) | No persistent per-series/per-author voice memory; session-local exception only | Accepted |
| [0011](0011-pyinstaller-packaging-no-code-signing.md) | PyInstaller single `.exe`, no code signing purchased | Accepted |
| [0012](0012-retain-copyleft-dependencies.md) | Retain `mutagen` (GPL) and `ebooklib` (AGPL) rather than replace them | Accepted |
| [0013](0013-epub-only-input-format.md) | Accept `.epub` input only; validate content, not extension | Accepted |
| [0014](0014-reuse-existing-implementations-by-default.md) | Reuse existing implementations by default; write new code only where there's a concrete reason | Accepted |
