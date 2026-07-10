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

from flask import Flask, Response, current_app, jsonify, request

from backend import bridge, dialogs
from pipeline.audit_logger import AuditLogRepository
from pipeline.batch_runner import BatchRunner
from pipeline.config import SettingsRepository
from pipeline.input_validation import DEFAULT_MAX_FILES
from pipeline.state_manager import StateRepository
from pipeline.tts_engine import TTSEngine

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
    tts_engine: TTSEngine,
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
    tts_engine: TTSEngine
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
    appdata_dir: Path, tts_engine: TTSEngine | None = None
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


def create_app(
    *, appdata_dir: Path | None = None, tts_engine: TTSEngine | None = None
) -> Flask:
    app = Flask(__name__)
    app.config["APP_STATE"] = _build_app_state(
        appdata_dir or DEFAULT_APPDATA_DIR, tts_engine
    )

    def _state() -> AppState:
        state: AppState = current_app.config["APP_STATE"]
        return state

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
            for f in uploaded:
                if not f.filename:
                    continue
                temp_path = Path(tmp) / f.filename
                f.save(temp_path)
                result = runner.add_book(temp_path)
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
    def retag_route(book_id: str) -> Response:
        body = request.get_json(silent=True) or {}
        overrides = body.get("overrides") or {}
        updated = _state().runner.retag_book(book_id, overrides)
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
        bundle = bridge.build_support_bundle(
            settings=state.settings,
            audit_log=state.audit_log,
            technical_error=body.get("technical_error", ""),
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
