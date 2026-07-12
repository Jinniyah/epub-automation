import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { LiveRegion } from "../components/shared/LiveRegion";
import { RemoveBookButton } from "../components/shared/RemoveBookButton";
import { requestSupportBundle } from "../api/client";

export interface ErrorScreenProps {
  summary: string;
  /** The book that's actually stuck, if the backend could identify one
   * -- almost always can (06-safety-error-handling.md's error payload
   * carries `book_id`). Without a way to remove *that* book, "Back to
   * Add Books" just re-polls into the same error again: the batch's
   * `state` stays "error" for as long as any book is still in `error`
   * status (`backend/bridge.py::derive_batch_state()`'s top-precedence
   * rule), so a real dead end until this button existed. */
  bookId?: string | null;
  bookLabel?: string;
  onBackToStart: () => void;
  onRemoved: () => void;
}

/** The generic "Something went wrong" screen
 * (06-safety-error-handling.md §Error communication) -- `summary` is
 * always the friendly, non-technical message the backend already
 * chose; the real technical detail only ever leaves the machine via
 * "Copy details for support," never over the polling response.
 */
export function ErrorScreen({
  summary,
  bookId,
  bookLabel,
  onBackToStart,
  onRemoved,
}: ErrorScreenProps) {
  const [bundlePath, setBundlePath] = useState<string | null>(null);

  async function copyDetails() {
    const result = await requestSupportBundle();
    setBundlePath(result.path);
  }

  return (
    <main aria-labelledby="error-heading">
      <h1 id="error-heading">Something went wrong</h1>
      <LiveRegion politeness="assertive">{summary}</LiveRegion>
      {bookId ? (
        <p className="caption">
          {bookLabel ?? "This book"} is the one causing trouble. You can remove
          it and carry on with the rest of your books.
        </p>
      ) : null}
      <BigButton variant="primary" onClick={onBackToStart}>
        Back to Add Books
      </BigButton>
      {bookId ? (
        <RemoveBookButton bookId={bookId} bookLabel={bookLabel ?? "this book"} onRemoved={onRemoved} />
      ) : null}
      <div className="stack-sm">
        <button type="button" className="link-button" onClick={() => void copyDetails()}>
          Copy details for support
        </button>
        {bundlePath ? <p className="caption">Saved to: {bundlePath}</p> : null}
      </div>
    </main>
  );
}
