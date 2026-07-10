"""Adversarial tests for pipeline/safe_zip.py's `SafeZipOperation` Template
Method -- crafted malicious fixtures, not just mocked inputs (docs/
requirements/09-testing-strategy.md §Priority coverage areas: "target
near-100%, with actual crafted malicious fixture files ... not just mocked
inputs").
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

from pipeline.safe_zip import (
    PathTraversalError,
    SafeZipOperation,
    XXEError,
    ZipBombError,
)


class _RecordingZipOperation(SafeZipOperation):
    """Minimal concrete subclass for testing -- records the names it saw
    once every guard passed, proving `_do_operation` only ever runs on a
    verified-safe zip."""

    def _do_operation(self, zf: zipfile.ZipFile) -> list[str]:
        return zf.namelist()


def _make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_a_normal_epub_like_zip_passes_every_guard(tmp_path: Path) -> None:
    zip_path = _make_zip(
        tmp_path / "book.epub",
        {
            "mimetype": b"application/epub+zip",
            "content.opf": b"<?xml version='1.0'?><package></package>",
            "chapter1.xhtml": b"<html><body>Hello</body></html>",
        },
    )

    result = _RecordingZipOperation(zip_path=zip_path).run()

    assert set(result) == {"mimetype", "content.opf", "chapter1.xhtml"}


def test_path_traversal_via_dotdot_is_rejected(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "evil.epub", {"../../etc/passwd": b"pwned"})

    with pytest.raises(PathTraversalError):
        _RecordingZipOperation(zip_path=zip_path).run()


def test_path_traversal_via_absolute_path_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil2.epub"
    # zipfile.writestr normalizes some absolute-looking names on write, so
    # construct the entry directly via ZipInfo to guarantee a leading "/"
    # survives into the archive's actual namelist().
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("/etc/passwd"), b"pwned")

    with pytest.raises(PathTraversalError):
        _RecordingZipOperation(zip_path=zip_path).run()


def test_zip_bomb_via_per_entry_size_cap_is_rejected(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "bomb1.epub", {"big.txt": b"x" * 1000})

    op = _RecordingZipOperation(
        zip_path=zip_path,
        max_uncompressed_entry_bytes=100,  # smaller than the 1000-byte entry
    )

    with pytest.raises(ZipBombError):
        op.run()


def test_zip_bomb_via_total_size_cap_is_rejected(tmp_path: Path) -> None:
    zip_path = _make_zip(
        tmp_path / "bomb2.epub",
        {"a.txt": b"x" * 60, "b.txt": b"x" * 60},
    )

    op = _RecordingZipOperation(
        zip_path=zip_path,
        max_uncompressed_entry_bytes=1000,
        max_uncompressed_total_bytes=100,  # smaller than 60 + 60
    )

    with pytest.raises(ZipBombError):
        op.run()


def test_zip_bomb_via_compression_ratio_is_rejected(tmp_path: Path) -> None:
    # A real, pathologically compressible payload -- highly repetitive
    # data compresses to a tiny fraction of its uncompressed size, which
    # is exactly the classic zip-bomb shape (a small file that expands
    # enormously), not a mocked file_size attribute.
    zip_path = tmp_path / "bomb3.epub"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge.txt", b"0" * 10_000_000)

    op = _RecordingZipOperation(
        zip_path=zip_path,
        max_uncompressed_entry_bytes=10**9,  # large enough to not trip this cap
        max_uncompressed_total_bytes=10**9,
        max_compression_ratio=50,  # real ratio here is far higher than 50x
    )

    with pytest.raises(ZipBombError):
        op.run()


def test_xxe_doctype_in_opf_is_rejected(tmp_path: Path) -> None:
    payload = (
        b"<?xml version='1.0'?>"
        b"<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
        b"<package>&xxe;</package>"
    )
    zip_path = _make_zip(tmp_path / "xxe.epub", {"content.opf": payload})

    with pytest.raises(XXEError):
        _RecordingZipOperation(zip_path=zip_path).run()


def test_xxe_entity_declaration_in_xhtml_is_rejected(tmp_path: Path) -> None:
    payload = b"<!ENTITY xxe SYSTEM 'file:///etc/passwd'><html>&xxe;</html>"
    zip_path = _make_zip(tmp_path / "xxe2.epub", {"chapter1.xhtml": payload})

    with pytest.raises(XXEError):
        _RecordingZipOperation(zip_path=zip_path).run()


def test_xxe_guard_allows_a_plain_html5_doctype_with_no_external_reference(
    tmp_path: Path,
) -> None:
    """A bare `<!DOCTYPE html>` -- what every real XHTML file (including
    ebooklib's own generated output) actually contains -- is not an XXE
    vector and must not be rejected. Regression test for a false positive
    found via pipeline/input_validation.py becoming this guard's first
    caller against realistic EPUB content."""
    payload = (
        b"<!DOCTYPE html>"
        b"<html><body><h1>Chapter 1</h1><p>Real content.</p></body></html>"
    )
    zip_path = _make_zip(tmp_path / "real.epub", {"chap1.xhtml": payload})

    result = _RecordingZipOperation(zip_path=zip_path).run()

    assert "chap1.xhtml" in result


def test_xxe_guard_rejects_doctype_with_external_system_reference(
    tmp_path: Path,
) -> None:
    """No literal `<!ENTITY` in this file's own bytes -- the danger is a
    blind fetch of externally-hosted entities -- so this must still be
    caught by the DOCTYPE check itself, not the (separate) ENTITY check."""
    payload = b'<!DOCTYPE foo SYSTEM "http://evil.example/evil.dtd"><foo/>'
    zip_path = _make_zip(tmp_path / "external.epub", {"content.opf": payload})

    with pytest.raises(XXEError):
        _RecordingZipOperation(zip_path=zip_path).run()


def test_xxe_guard_ignores_non_xml_members(tmp_path: Path) -> None:
    """A DOCTYPE-shaped string inside a non-XML member (e.g. a plain text
    or binary asset) is not a real XXE vector and must not be flagged --
    the guard only inspects members with an XML-ish extension."""
    zip_path = _make_zip(
        tmp_path / "ok.epub",
        {"notes.txt": b"<!DOCTYPE this is just text, not real xml>"},
    )

    result = _RecordingZipOperation(zip_path=zip_path).run()

    assert "notes.txt" in result


def test_guard_order_is_path_traversal_then_bomb_then_xxe(tmp_path: Path) -> None:
    """A zip with both a path-traversal entry and an XXE payload must fail
    on the path-traversal guard first -- proving `run()`'s fixed order,
    not just that each guard works in isolation."""
    with zipfile.ZipFile(tmp_path / "both.epub", "w") as zf:
        zf.writestr(zipfile.ZipInfo("../escape.txt"), b"pwned")
        zf.writestr(
            "content.opf",
            b"<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>",
        )

    with pytest.raises(PathTraversalError):
        _RecordingZipOperation(zip_path=tmp_path / "both.epub").run()


def test_do_operation_only_runs_after_every_guard_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = _make_zip(tmp_path / "safe.epub", {"a.txt": b"hello"})
    calls: list[str] = []

    class _Tracking(SafeZipOperation):
        def _do_operation(self, zf: zipfile.ZipFile) -> Any:
            calls.append("do_operation")
            return None

    _Tracking(zip_path=zip_path).run()

    assert calls == ["do_operation"]
