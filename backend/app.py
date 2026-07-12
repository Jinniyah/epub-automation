"""Flask API app factory -- JSON API routes (ADR-0001, docs/design/
PATTERNS.md §1).

Zero business logic belongs here -- every route is a thin translation
between an HTTP request/response and a call into `backend/bridge.py` or
`pipeline/batch_runner.py`'s `BatchRunner`. If a route body does anything
beyond parsing the request and shaping the response, that's a bug, not a
style preference (the same rule ADR-0001 states for `main.py`'s CLI).

One `BatchRunner` lives per Flask app instance at a time (single-user,
single-machine, ADR-0008) -- once its batch reaches `done`
(01-architecture.md §State derivation), adding a new book transparently
starts a fresh one; see `_current_runner()`.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from backend import bridge, dialogs
from pipeline.audit_logger import AuditLogRepository
from pipeline.batch_runner import STATUS_ERROR, BatchRunner
from pipeline.config import SettingsRepository
from pipeline.input_validation import DEFAULT_MAX_FILES
from pipeline.state_manager import StateRepository
from pipeline.tts_engine import (
    VOICES,
    TTSEngine,
    TTSEngineLike,
    ensure_voice_samples,
    installed_kokoro_version,
)

# A route handler may return either a bare JSON Response or a
# (Response, status_code) tuple -- Flask's own accepted return shape.
RouteResult = Response | tuple[Response, int]

DEFAULT_APPDATA_DIR = Path.home() / "AppData" / "Roaming" / "EpubAutomation"

# ai_api_key is masked like a password field everywhere in her UI
# (03-gui-ux-design.md) -- GET /api/settings never returns its real value.
_SECRET_SETTINGS_KEYS = frozenset({"ai_api_key"})


def _build_runner(
    *,
    appdata_dir: Path,
    settings: dict[str, Any],
    state_repo: StateRepository,
    audit_log: AuditLogRepository,
    tts_engine: TTSEngineLike,
) -> BatchRunner:
    output_folder = Path(settings.get("output_folder") or (appdata_dir / "Output"))
    return BatchRunner(
        library_root=appdata_dir / "Library",
        output_folder=output_folder,
        report_dir=appdata_dir / "logs",
        state_repo=state_repo,
        audit_log=audit_log,
        settings=settings,
        tts_engine=tts_engine,
        max_files=DEFAULT_MAX_FILES,
    )


@dataclass
class AppState:
    """Everything a request handler needs, constructed once per app and
    stashed on `app.config` -- not global module state, so multiple app
    instances (tests) never share it."""

    appdata_dir: Path
    settings_repo: SettingsRepository
    state_repo: StateRepository
    audit_log: AuditLogRepository
    tts_engine: TTSEngineLike
    settings: dict[str, Any]
    runner: BatchRunner

    def new_runner(self) -> BatchRunner:
        return _build_runner(
            appdata_dir=self.appdata_dir,
            settings=self.settings,
            state_repo=self.state_repo,
            audit_log=self.audit_log,
            tts_engine=self.tts_engine,
        )


def _build_app_state(
    appdata_dir: Path, tts_engine: TTSEngineLike | None = None
) -> AppState:
    settings_repo = SettingsRepository(appdata_dir / "settings.json")
    settings = settings_repo.load()
    state_repo = StateRepository(appdata_dir / "state.json")
    state_repo.load()
    audit_log = AuditLogRepository(appdata_dir / "audit_log.csv")
    engine = tts_engine or TTSEngine()

    return AppState(
        appdata_dir=appdata_dir,
        settings_repo=settings_repo,
        state_repo=state_repo,
        audit_log=audit_log,
        tts_engine=engine,
        settings=settings,
        runner=_build_runner(
            appdata_dir=appdata_dir,
            settings=settings,
            state_repo=state_repo,
            audit_log=audit_log,
            tts_engine=engine,
        ),
    )


def _current_runner(state: AppState) -> BatchRunner:
    """Once the current batch is fully `done`, the next book she adds
    starts a fresh batch rather than being silently appended to a
    finished one (03-gui-ux-design.md: "Yes" moves to the next book or
    ends the run; ending the run means back to a clean Screen 1)."""
    if bridge.derive_batch_state(state.runner.snapshot()) == bridge.BATCH_DONE:
        state.runner = state.new_runner()
    return state.runner


def _safe_upload_path(tmp_dir: Path, index: int, client_filename: str) -> Path:
    """A safe, unique path inside `tmp_dir` to save one uploaded file to.

    `client_filename` is fully attacker-controlled (whatever a multipart
    upload's `filename` field claims, from any origin -- see the CSRF/
    Origin check below) and must never be used to build a filesystem path
    directly: a value like `..\\..\\..\\evil.epub`, or a full absolute
    path such as `C:\\Users\\<name>\\...\\Startup\\evil.exe`, would
    otherwise let an upload write anywhere the process can write --
    `pathlib` silently discards the left-hand side of `/` entirely when
    the right-hand side is itself absolute. `secure_filename()` strips
    path separators, drive letters, and `..` segments; the `index`
    prefix keeps two uploads that happen to collide after sanitizing
    (e.g. two non-ASCII names both becoming empty) from overwriting each
    other within the same request.
    """
    safe_name = secure_filename(client_filename) or "upload"
    candidate = (tmp_dir / f"{index}_{safe_name}").resolve()
    if tmp_dir.resolve() not in candidate.parents:
        # Should be unreachable given secure_filename() above -- fail
        # closed rather than silently writing somewhere unexpected if a
        # future change ever weakens that guarantee.
        raise ValueError(
            f"Refusing to save upload outside the temp directory: {candidate}"
        )
    return candidate


# Methods that change state -- everything else (GET) is side-effect-free
# and doesn't need an Origin check.
_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


def _origin_is_allowed(origin: str | None, host: str) -> bool:
    """CSRF/DNS-rebinding guard for a localhost-only, unauthenticated
    API (ADR-0008). There's no login here to steal a session from, but a
    malicious or compromised webpage open in *another browser tab* can
    still issue a same-machine cross-origin request to this server --
    `multipart/form-data` and body-less POSTs don't trigger a CORS
    preflight, so the browser sends them regardless of what this server's
    response says. Real browsers always set `Origin` on a cross-origin
    fetch/XHR/form POST and cannot be scripted to omit or forge it, so
    requiring it to match the address this request actually arrived on
    (`request.host`, e.g. `"127.0.0.1:54321"`) blocks any other origin --
    including a page served from this same app on a *different* port --
    while still allowing this app's own future frontend (served from the
    same origin) and non-browser tools (curl, the CLI's own eventual test
    harness) that don't send `Origin` at all.

    Dev note (Epic 7): the Vite dev server runs on its own port, separate
    from Flask's dynamically-assigned one, which makes a raw dev-time
    `fetch()` genuinely cross-origin and therefore rejected here by
    design. Fix it on the frontend side (Vite proxy + Origin-header
    rewrite, see `frontend/README.md`) -- do not relax this check itself,
    since dev and prod share this same code path.
    """
    if origin is None:
        return True
    return origin == f"http://{host}"


def create_app(
    *, appdata_dir: Path | None = None, tts_engine: TTSEngineLike | None = None
) -> Flask:
    app = Flask(__name__)
    app.config["APP_STATE"] = _build_app_state(
        appdata_dir or DEFAULT_APPDATA_DIR, tts_engine
    )

    def _state() -> AppState:
        state: AppState = current_app.config["APP_STATE"]
        return state

    @app.before_request
    def _reject_cross_origin_mutations() -> RouteResult | None:
        if request.method in _MUTATING_METHODS and not _origin_is_allowed(
            request.headers.get("Origin"), request.host
        ):
            return (
                jsonify({"ok": False, "error": "Cross-origin request rejected."}),
                403,
            )
        return None

    @app.get("/api/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # Status polling (01-architecture.md §Status endpoint contract)
    # ------------------------------------------------------------------

    @app.get("/api/status")
    def status() -> Response:
        return jsonify(bridge.build_status_response(_state().runner))

    # ------------------------------------------------------------------
    # Settings (05-data-settings-and-logging.md)
    # ------------------------------------------------------------------

    @app.get("/api/settings")
    def get_settings() -> Response:
        state = _state()
        masked = {
            k: v for k, v in state.settings.items() if k not in _SECRET_SETTINGS_KEYS
        }
        masked["has_ai_api_key"] = bool(state.settings.get("ai_api_key"))
        return jsonify(masked)

    @app.post("/api/settings")
    def update_settings() -> Response:
        state = _state()
        body = request.get_json(silent=True) or {}
        # `state.settings` is the same dict object `settings_repo.load()`
        # returned (its own `self._data`), so mutating it in place here is
        # exactly what `save()` below then persists -- no separate
        # write-back step needed.
        for key, value in body.items():
            if key == "schema_version":
                continue
            state.settings[key] = value
        state.settings_repo.save()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Native folder pickers (ADR-0006)
    # ------------------------------------------------------------------

    @app.post("/api/dialogs/folder")
    def pick_folder_route() -> Response:
        body = request.get_json(silent=True) or {}
        path = dialogs.pick_folder(
            title=body.get("title", ""), initial_dir=body.get("initial_dir", "")
        )
        return jsonify({"path": path})

    def _open_folder_response(path: str | None) -> Response:
        opened = dialogs.open_folder(path) if path else False
        if not opened:
            return jsonify({"ok": False, "error": "That folder couldn't be found."})
        return jsonify({"ok": True})

    @app.post("/api/books/<book_id>/open-folder")
    def open_book_folder_route(book_id: str) -> Response:
        """ "📂 See the audiobook files" (03-gui-ux-design.md §Screen:
        Review) -- opens *this book's own* subfolder, resolved
        server-side from its already-tracked `output_audio_folder`
        rather than trusting a client-supplied path. No file path is
        ever sent to or from the browser for this
        (03-gui-ux-design.md's own "What is explicitly NOT exposed to
        her" rule -- "any file paths other than the two folders she
        picked")."""
        book = next(
            (b for b in _state().runner.snapshot() if b.book_id == book_id), None
        )
        path = book.data.get("output_audio_folder") if book else None
        return _open_folder_response(path)

    @app.post("/api/open-output-folder")
    def open_output_folder_route() -> Response:
        """ "📂 See all my finished books" -- her remembered
        `output_folder`, same path-hiding reasoning as above."""
        return _open_folder_response(_state().settings.get("output_folder"))

    # ------------------------------------------------------------------
    # Screen 1: Add Books
    # ------------------------------------------------------------------

    @app.post("/api/books")
    def add_books() -> Response:
        state = _state()
        runner = _current_runner(state)
        uploaded = request.files.getlist("files")
        results = []
        with tempfile.TemporaryDirectory(prefix="epub-automation-upload-") as tmp:
            tmp_dir = Path(tmp)
            for i, f in enumerate(uploaded):
                if not f.filename:
                    continue
                temp_path = _safe_upload_path(tmp_dir, i, f.filename)
                f.save(temp_path)
                result = runner.add_book(temp_path, original_filename=f.filename)
                results.append(
                    {
                        "ok": result.ok,
                        "original_filename": f.filename,
                        "book_id": result.book.book_id if result.book else None,
                        "reason": result.reason.value if result.reason else None,
                        "message": result.message,
                    }
                )
        return jsonify({"results": results})

    @app.delete("/api/books/<book_id>")
    def remove_book_route(book_id: str) -> Response:
        removed = _state().runner.remove_book(book_id)
        return jsonify({"ok": removed})

    @app.get("/api/disk-space")
    def disk_space_route() -> Response:
        report = _state().runner.disk_space_report()
        return jsonify(
            {
                "estimated_total_bytes": report.estimated_total_bytes,
                "any_insufficient": report.any_insufficient,
                "checked_paths": [
                    {
                        "path": str(check.path),
                        "free_bytes": check.free_bytes,
                        "sufficient": check.sufficient,
                    }
                    for check in report.checked_paths.values()
                ],
            }
        )

    # ------------------------------------------------------------------
    # Batch lifecycle
    # ------------------------------------------------------------------

    @app.post("/api/batch/start")
    def start_batch() -> Response:
        _state().runner.start()
        return jsonify({"ok": True})

    @app.post("/api/batch/start-generation")
    def start_generation_route() -> Response:
        _state().runner.start_generation()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Per-book identification loop
    # ------------------------------------------------------------------

    @app.post("/api/books/<book_id>/confirm")
    def confirm_metadata_route(book_id: str) -> RouteResult:
        body = request.get_json(silent=True) or {}
        try:
            updated = _state().runner.confirm_metadata(
                book_id, corrections=body.get("corrections")
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "status": updated.status})

    # ------------------------------------------------------------------
    # Voice assignment
    # ------------------------------------------------------------------

    @app.post("/api/books/<book_id>/voice")
    def assign_voice_route(book_id: str) -> RouteResult:
        body = request.get_json(silent=True) or {}
        voice = body.get("voice")
        if not voice:
            return jsonify({"ok": False, "error": "voice is required"}), 400
        try:
            updated = _state().runner.assign_voice(book_id, voice)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "voice": updated.data.get("voice")})

    @app.post("/api/books/<book_id>/metadata")
    def update_metadata_route(book_id: str) -> RouteResult:
        """The multi-book voice table's clickable book title
        (03-gui-ux-design.md §Voice assignment) -- corrects title/author/
        series while a book sits at `voice_pick`, distinct from the
        identification loop's `confirm` route above (which only accepts
        a book still awaiting confirmation) and from `retag` below
        (which rewrites already-generated files on disk)."""
        body = request.get_json(silent=True) or {}
        corrections = body.get("corrections") or {}
        try:
            updated = _state().runner.update_metadata(book_id, corrections)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "status": updated.status})

    # ------------------------------------------------------------------
    # Voice picker (03-gui-ux-design.md §Voice assignment) -- Epic 8
    # addition; see bridge.py::voice_choices() docstring. GET /api/voices
    # is also this app's chosen trigger point for the lazy voice-sample
    # cache build (opening the voice picker, per 04-tts-engine.md's
    # "a real audio-stage run, or her opening the voice picker" -- the
    # first call after a `kokoro` upgrade blocks on regenerating all 28
    # samples; every call after that is a cheap version-tag check).
    # ------------------------------------------------------------------

    @app.get("/api/voices")
    def voices_route() -> Response:
        state = _state()
        ensure_voice_samples(
            state.appdata_dir / "voice_samples",
            state.tts_engine,
            installed_kokoro_version(),
        )
        return jsonify({"voices": bridge.voice_choices()})

    @app.get("/api/voice-samples/<voice>")
    def voice_sample_route(voice: str) -> RouteResult:
        if voice not in VOICES:
            return jsonify({"ok": False, "error": "Unknown voice."}), 404
        sample_path = _state().appdata_dir / "voice_samples" / f"{voice}.mp3"
        if not sample_path.exists():
            return (
                jsonify({"ok": False, "error": "Voice sample not available yet."}),
                404,
            )
        return send_file(sample_path, mimetype="audio/mpeg")

    # ------------------------------------------------------------------
    # Pause / Cancel
    # ------------------------------------------------------------------

    @app.post("/api/books/<book_id>/pause")
    def pause_route(book_id: str) -> Response:
        _state().runner.request_pause(book_id)
        return jsonify({"ok": True})

    @app.post("/api/books/<book_id>/cancel")
    def cancel_route(book_id: str) -> Response:
        body = request.get_json(silent=True) or {}
        keep_partial = bool(body.get("keep_partial", True))
        updated = _state().runner.request_cancel(book_id, keep_partial=keep_partial)
        return jsonify({"ok": True, "status": updated.status})

    # ------------------------------------------------------------------
    # Output collision
    # ------------------------------------------------------------------

    @app.post("/api/books/<book_id>/collision")
    def resolve_collision_route(book_id: str) -> RouteResult:
        body = request.get_json(silent=True) or {}
        choice = body.get("choice")
        if choice not in ("replace", "keep_both"):
            return (
                jsonify({"ok": False, "error": "choice must be replace or keep_both"}),
                400,
            )
        try:
            updated = _state().runner.resolve_collision(book_id, choice)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "status": updated.status})

    # ------------------------------------------------------------------
    # Review + "No, let me fix it" (retag)
    # ------------------------------------------------------------------

    @app.post("/api/books/<book_id>/review")
    def review_route(book_id: str) -> RouteResult:
        body = request.get_json(silent=True) or {}
        looks_good = bool(body.get("looks_good"))
        try:
            updated = _state().runner.review_result(book_id, looks_good=looks_good)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 409
        return jsonify({"ok": True, "status": updated.status})

    @app.post("/api/books/<book_id>/retag")
    def retag_route(book_id: str) -> RouteResult:
        body = request.get_json(silent=True) or {}
        overrides = body.get("overrides") or {}
        updated = _state().runner.retag_book(book_id, overrides)
        if updated.status == STATUS_ERROR:
            error = updated.data.get("error", "Retag failed.")
            return jsonify({"ok": False, "error": error}), 422
        return jsonify({"ok": True, "status": updated.status})

    # ------------------------------------------------------------------
    # "What voice did I use before?" (03-gui-ux-design.md §Settings areas)
    # ------------------------------------------------------------------

    @app.get("/api/voice-history")
    def voice_history_route() -> RouteResult:
        try:
            history = bridge.voice_history(_state().audit_log)
        except bridge.VoiceHistoryUnavailable:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Something went wrong finding your voice history.",
                    }
                ),
                500,
            )
        return jsonify({"ok": True, "history": history})

    # ------------------------------------------------------------------
    # Error communication (06-safety-error-handling.md §Error communication)
    # ------------------------------------------------------------------

    @app.post("/api/support-bundle")
    def support_bundle_route() -> Response:
        state = _state()
        body = request.get_json(silent=True) or {}
        # The client can supply extra context (e.g. what she was doing
        # when she pressed the button), but the *real* error text comes
        # from the runner's own live state -- build_status_response()
        # never exposes it, so the client has no way to already know it.
        technical_error = body.get("technical_error") or bridge.current_error_detail(
            state.runner.snapshot()
        )
        bundle = bridge.build_support_bundle(
            settings=state.settings,
            audit_log=state.audit_log,
            technical_error=technical_error,
        )
        out_path = state.appdata_dir / "logs" / "support_bundle.txt"
        bridge.write_support_bundle(out_path, bundle)
        return jsonify({"ok": True, "path": str(out_path)})

    # ------------------------------------------------------------------
    # "Welcome back" -- detection only for now. Full state-file-driven
    # resume (rebuilding a live BatchRunner from state.json) is Epic 8
    # scope, once the actual "Welcome back" screen exists to drive it
    # (docs/BACKLOG.md) -- this endpoint answers "is anything pending"
    # so that screen has something real to build against, without this
    # epic needing to solve full runner reconstruction.
    # ------------------------------------------------------------------

    @app.get("/api/welcome-back")
    def welcome_back_route() -> Response:
        pending = _state().state_repo.incomplete_book_ids()
        return jsonify({"pending_book_ids": pending})

    # ------------------------------------------------------------------
    # "Quit for now" -- stops the background server itself, not just the
    # browser tab (ADR-0001 explicitly requires this control to exist).
    # ------------------------------------------------------------------

    @app.post("/api/quit")
    def quit_route() -> Response:
        def _shutdown() -> None:
            time.sleep(0.25)  # let the HTTP response actually reach her first
            os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()
        return jsonify({"ok": True})

    return app
