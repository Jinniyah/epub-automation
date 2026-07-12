import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { LiveRegion } from "../components/shared/LiveRegion";
import { Overlay } from "../components/shared/Overlay";
import { useAriaLiveThrottled } from "../hooks/useAriaLiveThrottled";
import { useWorkingScreenView } from "../viewmodels/useWorkingScreenView";
import { cancelBook, pauseBook } from "../api/client";
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

  const fullStatusText = view.timeEstimateText
    ? `${message} ${view.timeEstimateText}, based on how this book is going so far.`
    : message;
  const announced = useAriaLiveThrottled(fullStatusText, view.progress);

  async function handlePause() {
    if (!activeBookId) return;
    await pauseBook(activeBookId);
    onChanged();
  }

  async function handleCancelChoice(keepPartial: boolean) {
    if (!activeBookId) return;
    await cancelBook(activeBookId, keepPartial);
    setConfirmingCancel(false);
    onChanged();
  }

  return (
    <main aria-labelledby="working-heading">
      <div className="stack-sm">
        <h1 id="working-heading">Working on: {view.bookTitle}</h1>
        <p className="caption">{view.bookIndexLabel}</p>
      </div>

      <div className="stack-sm">
        <LiveRegion politeness="polite">🔊 {announced}</LiveRegion>
        <p className="caption">It's okay to leave this open and come back later.</p>
      </div>

      <div className="button-row">
        <BigButton
          variant="amber"
          caption="Stop for now, come back anytime."
          onClick={() => void handlePause()}
        >
          Pause
        </BigButton>
        <BigButton
          variant="danger"
          caption="Stop working on this book completely."
          onClick={() => setConfirmingCancel(true)}
        >
          Cancel
        </BigButton>
      </div>

      <BigButton variant="plain" onClick={onQuit}>
        Quit for now
      </BigButton>

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
