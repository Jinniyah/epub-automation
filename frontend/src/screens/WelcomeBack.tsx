import { BigButton } from "../components/shared/BigButton";
import type { Book, BookStatus } from "../api/types";

export interface WelcomeBackProps {
  pendingBookIds: string[];
  /** Whatever the current status poll already knows about those books,
   * if anything -- see this module's own comment below for why this can
   * legitimately be empty. */
  books: Book[];
  onContinue: () => void;
  onNotNow: () => void;
}

function phraseFor(status: BookStatus): string {
  switch (status) {
    case "voice_pick":
      return "waiting on a voice choice";
    case "generating":
    case "paused":
      return "getting the audio ready";
    case "error":
      return "ran into a problem";
    case "complete":
      return "all finished";
    default:
      return "getting its info sorted";
  }
}

/** Shown before Screen 1 whenever the state file has something pending
 * (03-gui-ux-design.md §"Welcome back" screen) -- covers every way the
 * app could have stopped (Quit for now, a crash, lost power) alike,
 * since it's driven entirely by what's incomplete, not by detecting how
 * the previous session ended.
 *
 * `GET /api/welcome-back` only ever answers "is anything pending" (a
 * list of book ids) -- it does not reconstruct their titles/status
 * after a real backend restart (`CLAUDE.md`'s flagged open item: full
 * state-file-driven resume is separate, not-yet-built backend work).
 * When the current status poll still has these books loaded (the common
 * case -- she just closed the tab, the background process kept
 * running), this screen shows their real titles and phase. When it
 * doesn't (a genuine process restart with no reconstruction yet), it
 * degrades honestly to a count instead of inventing detail the backend
 * can't currently supply.
 */
export function WelcomeBack({
  pendingBookIds,
  books,
  onContinue,
  onNotNow,
}: WelcomeBackProps) {
  const known = pendingBookIds
    .map((id) => books.find((b) => b.id === id))
    .filter((b): b is Book => b !== undefined);

  return (
    <main aria-labelledby="welcome-back-heading">
      <h1 id="welcome-back-heading">📚 Welcome back!</h1>
      <p>You were in the middle of:</p>
      {known.length > 0 ? (
        <ul className="row-list">
          {known.map((book) => (
            <li key={book.id} className="row-list__item">
              📖 {book.title ?? book.original_filename} — {phraseFor(book.status)}
            </li>
          ))}
        </ul>
      ) : (
        <p>
          📖 {pendingBookIds.length} book{pendingBookIds.length === 1 ? "" : "s"} you
          hadn't finished yet
        </p>
      )}
      <div className="button-row">
        <BigButton variant="primary" onClick={onContinue}>
          Continue
        </BigButton>
        <BigButton variant="plain" onClick={onNotNow}>
          Not right now
        </BigButton>
      </div>
    </main>
  );
}
