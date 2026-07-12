"""Tests for backend/app.py -- the Flask JSON API routes.

Uses Flask's test client throughout; the TTS engine is always a fake
(never touches real Kokoro), and `dialogs.pick_folder` is always
monkeypatched (never opens a real Tk window -- no display in CI).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, cast

import pytest
from ebooklib import epub
from flask.testing import FlaskClient

import backend.bridge as bridge_module
import backend.dialogs as dialogs_module
from backend.app import _origin_is_allowed, _safe_upload_path, create_app
from pipeline.batch_runner import NeedsInputType

_LONG_TEXT = "Some real narrative content, sentence by sentence. " * 20


class _FakeTTSEngine:
    def generate(self, text: str, voice: str) -> bytes:
        return b"FAKE-MP3-" + b"-" * 2000

    def generate_voice_sample(self, voice: str) -> bytes:
        return self.generate("sample", voice)


def _make_epub_bytes(*, title: str = "Fated", author: str = "Benedict Jacka") -> bytes:
    book = epub.EpubBook()
    book.set_identifier("id-app-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
    chapter.content = f"<html><body><h1>Chapter 1</h1><p>{_LONG_TEXT}</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path: Path) -> FlaskClient:
    app = create_app(appdata_dir=tmp_path, tts_engine=_FakeTTSEngine())
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _never_opens_a_real_explorer_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """`dialogs.open_folder()` defaults to `os.startfile()` -- monkeypatched
    here for every test in this module, the same way `dialogs.pick_folder`
    already is, so running this suite never pops a real File Explorer
    window. Mirrors the real function's own exists-check so the
    ok:true/false assertions in the open-folder tests below still mean
    something."""
    monkeypatch.setattr(
        dialogs_module,
        "open_folder",
        lambda path, **kwargs: bool(path) and Path(path).is_dir(),
    )


def _add_book_via_api(
    client: FlaskClient, *, filename: str = "book.epub", **epub_kwargs: Any
) -> dict[str, Any]:
    data = _make_epub_bytes(**epub_kwargs)
    resp = client.post(
        "/api/books",
        data={"files": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    result = resp.get_json()["results"][0]
    assert result["ok"], result
    return cast("dict[str, Any]", result)


def _poll_status(client: FlaskClient) -> dict[str, Any]:
    resp = client.get("/api/status")
    assert resp.status_code == 200
    return cast("dict[str, Any]", resp.get_json())


def _wait_for_state(
    client: FlaskClient, predicate: Any, timeout: float = 5.0
) -> dict[str, Any]:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _poll_status(client)
        if predicate(status):
            return status
        time.sleep(0.02)
    raise AssertionError(f"condition not met within timeout, last status={status}")


# ---------------------------------------------------------------------------
# _origin_is_allowed -- the CSRF/Origin fix, tested directly
# ---------------------------------------------------------------------------


def test_origin_is_allowed_when_no_origin_header_present() -> None:
    """Non-browser clients (curl, the CLI) never send Origin at all --
    must not be blocked."""
    assert _origin_is_allowed(None, "127.0.0.1:54321") is True


def test_origin_is_allowed_when_it_matches_the_request_host() -> None:
    assert _origin_is_allowed("http://127.0.0.1:54321", "127.0.0.1:54321") is True


def test_origin_is_rejected_from_a_different_host() -> None:
    assert _origin_is_allowed("https://evil.example", "127.0.0.1:54321") is False


def test_origin_is_rejected_from_a_different_local_port() -> None:
    """A page served by this same app on a different port (or a second,
    unrelated local server) is still a different origin."""
    assert _origin_is_allowed("http://127.0.0.1:9999", "127.0.0.1:54321") is False


# ---------------------------------------------------------------------------
# Health / status
# ---------------------------------------------------------------------------


def test_health(client: FlaskClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_cross_origin_post_is_rejected(client: FlaskClient) -> None:
    resp = client.post("/api/quit", headers={"Origin": "https://evil.example"})

    assert resp.status_code == 403


def test_same_origin_post_is_allowed(client: FlaskClient) -> None:
    # A harmless, side-effect-free-on-an-empty-batch route -- deliberately
    # not /api/quit here, since that spawns a real background thread that
    # would otherwise outlive this test (see test_quit_route_... below for
    # the test that's actually responsible for verifying quit's own
    # behavior, and waits out that thread correctly).
    # Flask's test client's default Host header is "localhost" -- match it
    # so this genuinely proves a same-origin request still works, not just
    # that no Origin header was sent.
    resp = client.post("/api/batch/start", headers={"Origin": "http://localhost"})

    assert resp.status_code == 200


def test_cross_origin_get_is_not_blocked(client: FlaskClient) -> None:
    """The Origin check only applies to mutating methods -- a read-only
    GET (e.g. polling status from a legitimate future frontend embedded
    differently) is never blocked by it."""
    resp = client.get("/api/status", headers={"Origin": "https://evil.example"})

    assert resp.status_code == 200


def test_status_is_idle_for_a_fresh_app(client: FlaskClient) -> None:
    status = _poll_status(client)
    assert status["state"] == "idle"
    assert status["books"] == []


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_get_settings_never_returns_the_real_api_key(client: FlaskClient) -> None:
    client.post("/api/settings", json={"ai_api_key": "sk-super-secret"})

    resp = client.get("/api/settings")

    body = resp.get_json()
    assert "ai_api_key" not in body
    assert body["has_ai_api_key"] is True


def test_settings_persist_to_disk(client: FlaskClient, tmp_path: Path) -> None:
    client.post("/api/settings", json={"books_folder": "C:\\Books"})

    import json

    on_disk = json.loads((tmp_path / "settings.json").read_text())
    assert on_disk["books_folder"] == "C:\\Books"


def test_settings_update_ignores_schema_version_from_the_client(
    client: FlaskClient,
) -> None:
    resp = client.post("/api/settings", json={"schema_version": 999})

    assert resp.status_code == 200
    assert client.get("/api/settings").get_json()["schema_version"] == 1


# ---------------------------------------------------------------------------
# Native folder picker (always monkeypatched -- never a real Tk window)
# ---------------------------------------------------------------------------


def test_pick_folder_route_returns_the_chosen_path(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dialogs_module, "pick_folder", lambda **kwargs: "C:\\Users\\Mom\\Books"
    )

    resp = client.post("/api/dialogs/folder", json={"title": "Where are your books?"})

    assert resp.get_json() == {"path": "C:\\Users\\Mom\\Books"}


def test_pick_folder_route_returns_none_when_cancelled(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dialogs_module, "pick_folder", lambda **kwargs: None)

    resp = client.post("/api/dialogs/folder", json={})

    assert resp.get_json() == {"path": None}


def test_open_output_folder_route_opens_her_remembered_output_folder(
    client: FlaskClient, tmp_path: Path
) -> None:
    client.post("/api/settings", json={"output_folder": str(tmp_path)})

    resp = client.post("/api/open-output-folder")

    assert resp.get_json() == {"ok": True}


def test_open_output_folder_route_degrades_gracefully_when_missing(
    client: FlaskClient, tmp_path: Path
) -> None:
    client.post("/api/settings", json={"output_folder": str(tmp_path / "gone")})

    resp = client.post("/api/open-output-folder")

    assert resp.get_json()["ok"] is False


def test_open_book_folder_route_opens_that_books_own_subfolder(
    client: FlaskClient, tmp_path: Path
) -> None:
    added = _add_book_via_api(client)
    book_id = added["book_id"]
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["needs_input"] is not None)
    client.post(f"/api/books/{book_id}/confirm", json={})
    _wait_for_state(client, lambda s: s["state"] == "voice_pick")
    client.post(f"/api/books/{book_id}/voice", json={"voice": "af_heart"})
    status = _wait_for_state(
        client,
        lambda s: s["needs_input"] is not None
        and s["needs_input"]["type"] == NeedsInputType.REVIEW_RESULT,
    )
    assert status["state"] == "review"

    resp = client.post(f"/api/books/{book_id}/open-folder")

    assert resp.get_json() == {"ok": True}


def test_open_book_folder_route_degrades_gracefully_for_an_unknown_book(
    client: FlaskClient,
) -> None:
    resp = client.post("/api/books/does-not-exist/open-folder")

    assert resp.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# _safe_upload_path -- the path-traversal fix, tested directly
# ---------------------------------------------------------------------------


def test_safe_upload_path_stays_inside_tmp_dir_for_traversal_attempts(
    tmp_path: Path,
) -> None:
    result = _safe_upload_path(tmp_path, 0, "..\\..\\..\\evil.epub")

    assert tmp_path in result.parents


def test_safe_upload_path_stays_inside_tmp_dir_for_an_absolute_filename(
    tmp_path: Path,
) -> None:
    result = _safe_upload_path(tmp_path, 0, "C:\\Windows\\Temp\\evil.dll")

    assert tmp_path in result.parents


def test_safe_upload_path_indexes_avoid_collisions(tmp_path: Path) -> None:
    a = _safe_upload_path(tmp_path, 0, "book.epub")
    b = _safe_upload_path(tmp_path, 1, "book.epub")

    assert a != b


# ---------------------------------------------------------------------------
# Screen 1: Add Books
# ---------------------------------------------------------------------------


def test_add_book_accepts_a_valid_epub(client: FlaskClient) -> None:
    result = _add_book_via_api(client)

    assert result["book_id"]
    assert result["original_filename"] == "book.epub"


def test_add_book_status_poll_shows_the_true_filename_not_the_temp_upload_name(
    client: FlaskClient,
) -> None:
    """Regression test: `/api/status`'s `original_filename` must be her
    real filename, not the `<index>_<name>` collision-avoiding name
    `_safe_upload_path()` gives the temp file the upload is briefly
    saved as -- a real bug found via a live browser smoke test (the
    upload response's own `original_filename` was always correct, which
    is why this specific gap wasn't caught by
    `test_add_book_accepts_a_valid_epub` above)."""
    _add_book_via_api(client, filename="Fated.epub")

    status = _poll_status(client)

    assert status["books"][0]["original_filename"] == "Fated.epub"


def test_add_book_rejects_a_non_epub_file(client: FlaskClient) -> None:
    resp = client.post(
        "/api/books",
        data={"files": (io.BytesIO(b"not an epub"), "notes.txt")},
        content_type="multipart/form-data",
    )

    result = resp.get_json()["results"][0]
    assert result["ok"] is False
    assert result["reason"] == "not_epub"


def test_add_book_upload_filename_cannot_escape_the_temp_directory(
    tmp_path: Path, client: FlaskClient
) -> None:
    """Regression test: a crafted multipart filename must never let the
    upload write outside the request's own temp directory -- confirmed
    directly that pathlib silently discards the temp-dir prefix when the
    filename is itself absolute, before this fix was added."""
    outside_target = tmp_path / "should-not-exist.txt"
    data = _make_epub_bytes()

    resp = client.post(
        "/api/books",
        data={"files": (io.BytesIO(data), str(outside_target))},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    assert not outside_target.exists()


def test_add_book_upload_filename_with_traversal_sequences_is_sanitized(
    client: FlaskClient,
) -> None:
    data = _make_epub_bytes()

    resp = client.post(
        "/api/books",
        data={"files": (io.BytesIO(data), "..\\..\\..\\evil.epub")},
        content_type="multipart/form-data",
    )

    result = resp.get_json()["results"][0]
    assert result["ok"] is True  # still a valid, accepted EPUB once sanitized


def test_remove_book_route(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.delete(f"/api/books/{added['book_id']}")

    assert resp.get_json() == {"ok": True}
    assert _poll_status(client)["books"] == []


def test_disk_space_route(client: FlaskClient) -> None:
    _add_book_via_api(client)

    resp = client.get("/api/disk-space")

    body = resp.get_json()
    assert body["estimated_total_bytes"] > 0
    assert isinstance(body["checked_paths"], list)


# ---------------------------------------------------------------------------
# Full flow: start -> confirm -> voice (auto-generates for single book) ->
# review -> complete
# ---------------------------------------------------------------------------


def test_full_single_book_flow_reaches_review_then_complete(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)
    book_id = added["book_id"]

    resp = client.post("/api/batch/start")
    assert resp.get_json() == {"ok": True}

    status = _wait_for_state(client, lambda s: s["needs_input"] is not None)
    assert status["needs_input"]["book_id"] == book_id
    assert status["needs_input"]["type"] == NeedsInputType.CONFIRM_METADATA

    resp = client.post(f"/api/books/{book_id}/confirm", json={})
    assert resp.get_json()["ok"] is True

    _wait_for_state(client, lambda s: s["state"] == "voice_pick")
    resp = client.post(f"/api/books/{book_id}/voice", json={"voice": "af_heart"})
    assert resp.get_json()["ok"] is True

    status = _wait_for_state(
        client,
        lambda s: s["needs_input"] is not None
        and s["needs_input"]["type"] == NeedsInputType.REVIEW_RESULT,
    )
    assert status["state"] == "review"

    resp = client.post(f"/api/books/{book_id}/review", json={"looks_good": True})

    assert resp.get_json() == {"ok": True, "status": "complete"}
    assert _poll_status(client)["state"] == "done"


def test_confirm_metadata_on_unknown_stage_returns_409(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.post(f"/api/books/{added['book_id']}/confirm", json={})

    assert resp.status_code == 409


def test_assign_voice_requires_a_voice_field(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.post(f"/api/books/{added['book_id']}/voice", json={})

    assert resp.status_code == 400


def test_assign_voice_on_a_book_not_at_voice_pick_returns_409(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/voice", json={"voice": "af_heart"}
    )

    assert resp.status_code == 409


def test_update_metadata_route_patches_a_book_at_voice_pick(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["needs_input"] is not None)
    client.post(f"/api/books/{added['book_id']}/confirm", json={})
    _wait_for_state(
        client, lambda s: all(b["status"] == "voice_pick" for b in s["books"])
    )

    resp = client.post(
        f"/api/books/{added['book_id']}/metadata",
        json={"corrections": {"title": "Corrected Title"}},
    )

    assert resp.get_json() == {"ok": True, "status": "voice_pick"}
    status = _poll_status(client)
    assert status["books"][0]["title"] == "Corrected Title"


def test_update_metadata_route_on_a_book_not_at_voice_pick_returns_409(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/metadata",
        json={"corrections": {"title": "New"}},
    )

    assert resp.status_code == 409


def test_resolve_collision_rejects_an_invalid_choice(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/collision", json={"choice": "not_a_real_choice"}
    )

    assert resp.status_code == 400


def test_resolve_collision_with_no_pending_collision_returns_409(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/collision", json={"choice": "replace"}
    )

    assert resp.status_code == 409


def test_review_with_no_pending_review_returns_409(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/review", json={"looks_good": True}
    )

    assert resp.status_code == 409


def test_retag_route_applies_overrides_after_review_no(client: FlaskClient) -> None:
    added = _add_book_via_api(client)
    book_id = added["book_id"]
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["needs_input"] is not None)
    client.post(f"/api/books/{book_id}/confirm", json={})
    _wait_for_state(client, lambda s: s["state"] == "voice_pick")
    client.post(f"/api/books/{book_id}/voice", json={"voice": "af_heart"})
    _wait_for_state(
        client,
        lambda s: s["needs_input"] is not None
        and s["needs_input"]["type"] == NeedsInputType.REVIEW_RESULT,
    )
    client.post(f"/api/books/{book_id}/review", json={"looks_good": False})

    resp = client.post(
        f"/api/books/{book_id}/retag", json={"overrides": {"title": "Corrected"}}
    )

    body = resp.get_json()
    assert body == {"ok": True, "status": "complete"}


def test_retag_route_reports_failure_when_retag_itself_fails(
    client: FlaskClient,
) -> None:
    """Regression test: a genuinely failed retag (e.g. no audio_folder to
    retag yet) must not be reported as ok:true -- previously this route
    always returned ok:true regardless of RetagStage's own result."""
    added = _add_book_via_api(client)  # never started -- no audio_folder exists yet

    resp = client.post(f"/api/books/{added['book_id']}/retag", json={"overrides": {}})

    assert resp.status_code == 422
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"]


def test_start_generation_route_starts_a_multi_book_batch(client: FlaskClient) -> None:
    one = _add_book_via_api(client, filename="one.epub", title="One")
    two = _add_book_via_api(client, filename="two.epub", title="Two")
    client.post("/api/batch/start")
    _wait_for_state(
        client, lambda s: all(b["status"] == "needs_input" for b in s["books"])
    )
    client.post(f"/api/books/{one['book_id']}/confirm", json={})
    client.post(f"/api/books/{two['book_id']}/confirm", json={})
    _wait_for_state(
        client, lambda s: all(b["status"] == "voice_pick" for b in s["books"])
    )

    resp = client.post("/api/batch/start-generation")

    assert resp.get_json() == {"ok": True}
    _wait_for_state(client, lambda s: s["state"] == "working")


def test_adding_a_book_after_a_batch_is_done_starts_a_fresh_batch(
    client: FlaskClient,
) -> None:
    first = _add_book_via_api(client, filename="one.epub")
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["needs_input"] is not None)
    client.post(f"/api/books/{first['book_id']}/confirm", json={})
    _wait_for_state(client, lambda s: s["state"] == "voice_pick")
    client.post(f"/api/books/{first['book_id']}/voice", json={"voice": "af_heart"})
    _wait_for_state(
        client,
        lambda s: s["needs_input"] is not None
        and s["needs_input"]["type"] == NeedsInputType.REVIEW_RESULT,
    )
    client.post(f"/api/books/{first['book_id']}/review", json={"looks_good": True})
    assert _poll_status(client)["state"] == "done"

    second = _add_book_via_api(client, filename="two.epub")

    status = _poll_status(client)
    book_ids = {b["id"] for b in status["books"]}
    assert first["book_id"] not in book_ids  # old, finished batch is gone
    assert second["book_id"] in book_ids
    assert status["state"] == "idle" or status["state"] == "identifying"


# ---------------------------------------------------------------------------
# Pause / Cancel -- HTTP wiring only (BatchRunner's own behavior is
# covered exhaustively in tests/test_batch_runner.py)
# ---------------------------------------------------------------------------


def test_pause_route_is_accepted_even_for_a_book_not_yet_generating(
    client: FlaskClient,
) -> None:
    added = _add_book_via_api(client)

    resp = client.post(f"/api/books/{added['book_id']}/pause")

    assert resp.get_json() == {"ok": True}


def test_cancel_route_returns_the_new_status(client: FlaskClient) -> None:
    added = _add_book_via_api(client)

    resp = client.post(
        f"/api/books/{added['book_id']}/cancel", json={"keep_partial": True}
    )

    assert resp.get_json() == {"ok": True, "status": "cancelled"}


# ---------------------------------------------------------------------------
# Voice history
# ---------------------------------------------------------------------------


def test_voice_history_route_is_empty_for_a_fresh_install(client: FlaskClient) -> None:
    resp = client.get("/api/voice-history")

    assert resp.get_json() == {"ok": True, "history": []}


def test_voice_history_route_degrades_gracefully_when_log_unreadable(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(audit_log: Any) -> list[Any]:
        from backend.bridge import VoiceHistoryUnavailable

        raise VoiceHistoryUnavailable("disk error")

    monkeypatch.setattr(bridge_module, "voice_history", _boom)

    resp = client.get("/api/voice-history")

    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False


# ---------------------------------------------------------------------------
# Voice picker (03-gui-ux-design.md §Voice assignment)
# ---------------------------------------------------------------------------


def test_voices_route_returns_plain_first_names(client: FlaskClient) -> None:
    resp = client.get("/api/voices")

    body = resp.get_json()
    assert {"key": "af_heart", "name": "Heart"} in body["voices"]
    assert all("(" not in v["name"] for v in body["voices"])


def test_voices_route_builds_the_sample_cache(
    client: FlaskClient, tmp_path: Path
) -> None:
    client.get("/api/voices")

    assert (tmp_path / "voice_samples" / "af_heart.mp3").exists()
    assert (tmp_path / "voice_samples" / "version.txt").exists()


def test_voice_sample_route_serves_a_cached_sample(client: FlaskClient) -> None:
    client.get("/api/voices")  # populates the cache first

    resp = client.get("/api/voice-samples/af_heart")

    assert resp.status_code == 200
    assert resp.mimetype == "audio/mpeg"


def test_voice_sample_route_404s_for_an_unknown_voice(client: FlaskClient) -> None:
    resp = client.get("/api/voice-samples/not_a_real_voice")

    assert resp.status_code == 404


def test_voice_sample_route_404s_before_the_cache_is_built(
    client: FlaskClient,
) -> None:
    resp = client.get("/api/voice-samples/af_heart")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Support bundle
# ---------------------------------------------------------------------------


def test_support_bundle_route_writes_a_file_without_the_api_key(
    client: FlaskClient, tmp_path: Path
) -> None:
    client.post("/api/settings", json={"ai_api_key": "sk-secret"})

    resp = client.post("/api/support-bundle", json={"technical_error": "boom"})

    body = resp.get_json()
    assert body["ok"] is True
    content = Path(body["path"]).read_text(encoding="utf-8")
    assert "boom" in content
    assert "sk-secret" not in content


def test_support_bundle_route_finds_the_real_error_without_the_client_supplying_it(
    client: FlaskClient,
) -> None:
    """Regression test: build_status_response() never exposes a book's
    raw error text (by design -- 01-architecture.md), so the support
    bundle must go find it itself server-side rather than relying on the
    client already knowing something the API never told it."""
    import zipfile

    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip")  # valid zip, unreadable EPUB
    upload = client.post(
        "/api/books",
        data={"files": (io.BytesIO(broken.getvalue()), "broken.epub")},
        content_type="multipart/form-data",
    )
    assert upload.get_json()["results"][0]["ok"] is True
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["state"] == "error")

    resp = client.post("/api/support-bundle", json={})  # no technical_error supplied

    body = resp.get_json()
    content = Path(body["path"]).read_text(encoding="utf-8")
    assert "Could not read EPUB" in content


# ---------------------------------------------------------------------------
# Welcome back
# ---------------------------------------------------------------------------


def test_welcome_back_route_is_empty_for_a_fresh_install(client: FlaskClient) -> None:
    resp = client.get("/api/welcome-back")

    assert resp.get_json() == {"pending_book_ids": []}


def test_welcome_back_route_lists_a_book_mid_pipeline(client: FlaskClient) -> None:
    added = _add_book_via_api(client)
    client.post("/api/batch/start")
    _wait_for_state(client, lambda s: s["needs_input"] is not None)

    resp = client.get("/api/welcome-back")

    assert added["book_id"] in resp.get_json()["pending_book_ids"]


# ---------------------------------------------------------------------------
# Quit
# ---------------------------------------------------------------------------


def test_quit_route_responds_ok_without_actually_killing_the_test_process(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    exit_calls: list[int] = []
    monkeypatch.setattr(os, "_exit", exit_calls.append)

    resp = client.post("/api/quit")

    assert resp.get_json() == {"ok": True}
    # The actual process-exit call is deferred to a background thread
    # (so the HTTP response reaches her first) -- give it a moment, then
    # confirm it was our patched, harmless version that got called, not
    # a real process exit (which would have killed this test process).
    import time

    time.sleep(0.4)
    assert exit_calls == [0]
