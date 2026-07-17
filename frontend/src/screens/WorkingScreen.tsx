import { useEffect, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { LiveRegion } from "../components/shared/LiveRegion";
import { Overlay } from "../components/shared/Overlay";
import { useAriaLiveThrottled } from "../hooks/useAriaLiveThrottled";
import { useWorkingScreenView } from "../viewmodels/useWorkingScreenView";
import { cancelBook, pauseBook, startGeneration } from "../api/client";
import type { Book } from "../api/types";

export interface WorkingScreenProps {
  books: Book[];
  activeBookId: string | null;
  message: string;
  onChanged: () => void;
  onQuit: () => void;
}

function CancelConfirmDialog({
  bookTitle,
  onChoose,
  onClose,
}: {
  bookTitle: string;
  onChoose: (keepPartial: boolean) => void;
  onClose: () => void;
}) {
  return (
    <Overlay
      titleId="cancel-heading"
      title={`Stop working on "${bookTitle}"?`}
      onClose={onClose}
    >
      <p>The audiobook won't be finished.</p>
      <div className="button-row">
        <BigButton variant="danger" onClick={() => onChoose(true)}>
          Stop, but keep what's done so far
        </BigButton>
        <BigButton variant="plain" onClick={() => onChoose(false)}>
          Stop and discard everything
        </BigButton>
      </div>
      <button type="button" className="link-button" onClick={onClose}>
        Never mind
      </button>
    </Overlay>
  );
}

/** §Screen: Working (03-gui-ux-design.md) -- shown per book while audio
 * generation is running. Closing the tab is safe (background Flask
 * process); Pause/Cancel are visually and semantically distinct so she
 * never mistakes one for the other.
 *
 * **Visual design system (docs/BACKLOG.md Epic 8.6):** the status block
 * is a `.card` -- a distinct, bounded "what's happening right now"
 * section, rather than status text and action buttons flowing together
 * undifferentiated. Pause/Cancel and Quit for now sit in a `.screen-
 * actions` sticky bottom bar, so the controls she's working toward stay
 * in the same place instead of scrolling away.
 *
 * **Pause/Cancel feedback (fixed 2026-07-17, real user report):**
 * `pipeline/batch_runner.py`'s pause/cancel were always functionally
 * correct -- `request_pause()`/`request_cancel()` just flag the request;
 * `AudioStage`'s `should_stop` hook only actually stops at the *next
 * chunk boundary*, so the book's status doesn't flip to `paused`/
 * `cancelled` until the next poll after that. The real gap was that this
 * screen never reflected any of it: clicking Pause looked identical to
 * not clicking anything, with no way to Resume afterward, and nothing
 * disabled the button in the meantime. Now: a `paused` book swaps Pause
 * for a real Resume button (`startGeneration()` already resumes a
 * paused book server-side -- see `BatchRunner.start_generation()`'s own
 * docstring, no new backend route needed) and shows a visible "Paused"
 * badge; Pause/Resume disable themselves the instant they're clicked and
 * only re-enable once the book's actual status confirms the change,
 * never re-clickable while the request is in flight. Cancel behaves the
 * same way -- confirming closes the dialog immediately and disables
 * both buttons while the cancellation is pending. No special-cased
 * "navigate home" logic was added for Cancel: once the cancelled book is
 * the last one in the batch, `derive_batch_state()` already flips the
 * top-level `state` to `done`, which `App.tsx` already routes back to
 * Screen 1 -- Cancel reaching "home" is a natural consequence of the
 * existing state machine, not a new frontend redirect. If other books
 * in the batch are still generating, this screen instead moves on to
 * the next active one, which is correct: the person shouldn't be bounced
 * out of Working while the rest of the batch is still running.
 *
 * **Chunk-progress readout (added 2026-07-17, real user request):**
 * closes docs/BACKLOG.md Epic 8.5's own "visible chunk-progress readout"
 * item -- `progress.chunks_done`/`chunks_total` were already in every
 * poll response, just never shown. "Working on file N of M..." (N is
 * the chunk currently in flight, `chunks_done + 1`, capped at the
 * total) sits directly under the friendly status line, paired with a
 * real `<progress>` bar rather than replacing the text
 * (`03-gui-ux-design.md`'s "never a bare percentage or spinner alone").
 * Deliberately a native `<progress>` element, not a styled `<div>`: a
 * dynamic-width fill bar would otherwise need the `style` prop for its
 * `width`, which `frontend/eslint.config.js` forbids app-wide
 * (docs/BACKLOG.md Epic 8.6) -- `<progress value max>` lets the browser
 * own the fill percentage and comes with built-in `role="progressbar"`/
 * `aria-valuenow` semantics for free, styled via `::-webkit-progress-*`/
 * `::-moz-progress-bar` pseudo-elements in index.css instead of inline
 * styles. Shown whenever chunk progress exists, paused or not, since a
 * paused book's last-known position is still useful context.
 */
export function WorkingScreen({
  books,
  activeBookId,
  message,
  onChanged,
  onQuit,
}: WorkingScreenProps) {
  const view = useWorkingScreenView(books, activeBookId);
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const activeBook = books.find((b) => b.id === activeBookId);
  const isPaused = activeBook?.status === "paused";

  // Once the book's real status confirms a pause/resume actually took
  // effect, the in-flight flag it was gating is no longer meaningful --
  // and a different book becoming active (e.g. after this one was
  // cancelled) means any in-flight flag for the *previous* book no
  // longer applies either.
  useEffect(() => {
    setPausing(false);
    setResuming(false);
    setCancelling(false);
  }, [activeBookId, isPaused]);

  const fullStatusText = isPaused
    ? "Paused. Press Resume whenever you're ready to continue."
    : view.timeEstimateText
      ? `${message} ${view.timeEstimateText}, based on how this book is going so far.`
      : message;
  const announced = useAriaLiveThrottled(fullStatusText, view.progress);

  const currentFileNumber = view.progress
    ? Math.min(view.progress.chunks_done + 1, view.progress.chunks_total)
    : null;

  async function handlePause() {
    if (!activeBookId) return;
    setPausing(true);
    await pauseBook(activeBookId);
    onChanged();
  }

  async function handleResume() {
    if (!activeBookId) return;
    setResuming(true);
    await startGeneration();
    onChanged();
  }

  async function handleCancelChoice(keepPartial: boolean) {
    if (!activeBookId) return;
    // Close the confirmation immediately -- she already answered it;
    // making her stare at the popup until the background cancel
    // actually lands (up to the current chunk finishing) would look
    // like the app ignored her answer.
    setConfirmingCancel(false);
    setCancelling(true);
    await cancelBook(activeBookId, keepPartial);
    onChanged();
  }

  return (
    <main aria-labelledby="working-heading">
      <div className="stack-sm">
        <h1 id="working-heading">Working on: {view.bookTitle}</h1>
        <p className="caption">{view.bookIndexLabel}</p>
      </div>

      <div className="card stack-sm">
        {isPaused ? (
          <p className="status-badge status-badge--amber">
            <span aria-hidden="true">⏸️</span> Paused
          </p>
        ) : null}
        <LiveRegion politeness="polite">🔊 {announced}</LiveRegion>
        <p className="caption">
          {isPaused
            ? "Press Resume whenever you're ready to continue."
            : "It's okay to leave this open and come back later."}
        </p>
        {view.progress && currentFileNumber !== null ? (
          <div className="stack-sm">
            <p>
              Working on file {currentFileNumber} of {view.progress.chunks_total}...
            </p>
            <progress
              className="progress-bar"
              value={view.progress.chunks_done}
              max={view.progress.chunks_total}
              aria-label={`File ${currentFileNumber} of ${view.progress.chunks_total}`}
            />
          </div>
        ) : null}
      </div>

      <div className="screen-actions stack-sm">
        <div className="button-row">
          {isPaused ? (
            <BigButton
              variant="primary"
              caption="Continue making this audiobook."
              disabled={resuming}
              onClick={() => void handleResume()}
            >
              {resuming ? "Resuming…" : "▶ Resume"}
            </BigButton>
          ) : (
            <BigButton
              variant="amber"
              caption="Stop for now, come back anytime."
              disabled={pausing || cancelling}
              onClick={() => void handlePause()}
            >
              {pausing ? "Pausing…" : "Pause"}
            </BigButton>
          )}
          <BigButton
            variant="danger"
            caption="Stop working on this book completely."
            disabled={cancelling}
            onClick={() => setConfirmingCancel(true)}
          >
            {cancelling ? "Stopping…" : "Cancel"}
          </BigButton>
        </div>

        <BigButton variant="plain" onClick={onQuit}>
          Quit for now
        </BigButton>
      </div>

      {confirmingCancel ? (
        <CancelConfirmDialog
          bookTitle={view.bookTitle}
          onChoose={(keepPartial) => void handleCancelChoice(keepPartial)}
          onClose={() => setConfirmingCancel(false)}
        />
      ) : null}
    </main>
  );
}
