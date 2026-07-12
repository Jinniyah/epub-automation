import { useState } from "react";
import { cancelBook } from "../../api/client";

export interface RemoveBookButtonProps {
  bookId: string;
  /** Falls back to the raw filename when title identification hasn't
   * happened yet (or failed) -- there's always something to say her
   * accessible name after. */
  bookLabel: string;
  onRemoved: () => void;
}

/** A single, obvious way to pull one book out of the batch, available
 * anywhere a book can get stuck or was added by mistake -- not just
 * Screen 1's pre-Start "Remove" (03-gui-ux-design.md's original scope),
 * since a real run surfaced that a book stuck on "Something went
 * wrong" had no way out at all. Uses the same `cancel` endpoint the
 * Working screen's Cancel button does -- it already accepts a book in
 * any status, not just `generating` (`pipeline/batch_runner.py::
 * request_cancel()`), so no backend change was needed, only surfacing
 * it here. Instant, no confirmation step, matching Screen 1's existing
 * Remove -- consistent with "generalize it, not add a second kind of
 * fussier removal."
 */
export function RemoveBookButton({ bookId, bookLabel, onRemoved }: RemoveBookButtonProps) {
  const [removing, setRemoving] = useState(false);

  async function handleClick() {
    setRemoving(true);
    try {
      await cancelBook(bookId);
      onRemoved();
    } finally {
      setRemoving(false);
    }
  }

  return (
    <button
      type="button"
      className="link-button link-button--danger"
      disabled={removing}
      aria-label={`Remove "${bookLabel}" from this batch`}
      onClick={() => void handleClick()}
    >
      ✕ Remove this book
    </button>
  );
}
