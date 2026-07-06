"""Proves the `Stage` interface itself is sufficient -- not a test of any
concrete stage (those land in Epics 2-5), but of the seam they'll all
implement. Per docs/design/PATTERNS.md §3: "a Stage test suite should
include at least one test that runs against a fake/minimal Stage
implementation to prove the interface itself is sufficient."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline.stage import BookState, Stage


@dataclass
class FakeStage:
    """The minimal possible Stage implementation -- toggled by a single
    settings key, and it flips `status` to prove `run()` was actually
    called and its return value is what the runner uses going forward."""

    name: str = "fake"
    toggle_key: str = "fake_enabled"

    def applies_to(self, book: BookState, settings: dict[str, Any]) -> bool:
        return bool(settings.get(self.toggle_key, True))

    def run(self, book: BookState) -> BookState:
        return BookState(book_id=book.book_id, status="fake-complete", data=book.data)


def test_fake_stage_satisfies_the_stage_protocol() -> None:
    stage: Stage = FakeStage()
    assert isinstance(stage, Stage)


def test_applies_to_respects_the_run_toggle() -> None:
    stage = FakeStage(toggle_key="fake_enabled")
    book = BookState(book_id="b1")

    assert stage.applies_to(book, {"fake_enabled": True}) is True
    assert stage.applies_to(book, {"fake_enabled": False}) is False
    # Missing toggle key defaults to True in this fake -- concrete stages
    # (Epic 2-5) define their own defaults; this just proves the seam
    # takes a plain settings dict and returns a plain bool.
    assert stage.applies_to(book, {}) is True


def test_run_returns_an_updated_book_state_without_mutating_the_input() -> None:
    stage = FakeStage()
    book = BookState(book_id="b1", status="pending", data={"title": "Fated"})

    updated = stage.run(book)

    assert updated.book_id == "b1"
    assert updated.status == "fake-complete"
    assert updated.data == {"title": "Fated"}
    # The input BookState itself is untouched -- a runner iterating
    # multiple stages must be able to trust that a stage's `run()` doesn't
    # secretly mutate the object it was handed.
    assert book.status == "pending"


def test_run_is_safe_to_call_again_on_an_already_processed_book() -> None:
    """Every Stage must be resumable (docs/requirements/06-safety-error-
    handling.md §Long-run resilience) -- calling run() twice on the same
    book must not raise or corrupt its state."""
    stage = FakeStage()
    book = BookState(book_id="b1")

    once = stage.run(book)
    twice = stage.run(once)

    assert twice.status == "fake-complete"
