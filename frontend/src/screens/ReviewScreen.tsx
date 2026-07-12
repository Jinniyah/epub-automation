import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { openBookFolder, openOutputFolder, submitReview } from "../api/client";
import type { Book } from "../api/types";
import { formatAuthor } from "../utils/authorName";

export interface ReviewScreenProps {
  book: Book;
  onDone: () => void;
  onFixIt: () => void;
}

/** §Screen: Review (03-gui-ux-design.md) -- shown once per book right
 * after its audio finishes. The book-scoped folder link sits above the
 * Yes/No question on purpose, so she can actually look at the real
 * chapter files before answering.
 */
export function ReviewScreen({ book, onDone, onFixIt }: ReviewScreenProps) {
  const [folderError, setFolderError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function openThisBooksFolder() {
    const result = await openBookFolder(book.id);
    setFolderError(result.ok ? null : "We couldn't open that folder.");
  }

  async function handleYes() {
    setSaving(true);
    try {
      await submitReview(book.id, true);
      onDone();
    } finally {
      setSaving(false);
    }
  }

  async function handleNo() {
    setSaving(true);
    try {
      await submitReview(book.id, false);
      onFixIt();
    } finally {
      setSaving(false);
    }
  }

  return (
    <main aria-labelledby="review-heading">
      <h1 id="review-heading">✅ {book.title ?? book.original_filename} is ready!</h1>

      <p>
        <strong>Author:</strong> {formatAuthor(book.author_first, book.author_last)}
      </p>
      <p>
        <strong>Title:</strong> {book.title}
      </p>
      {book.series ? (
        <p>
          <strong>Series:</strong> {book.series}
          {book.series_number ? ` #${book.series_number}` : ""}
        </p>
      ) : null}

      <button type="button" onClick={() => void openThisBooksFolder()}>
        📂 See the audiobook files
      </button>
      {folderError ? <p role="alert">{folderError}</p> : null}

      <p>Does the audiobook chapters look right or do they need renamed?</p>
      <BigButton variant="primary" disabled={saving} onClick={() => void handleYes()}>
        Yes, looks good
      </BigButton>
      <BigButton variant="plain" disabled={saving} onClick={() => void handleNo()}>
        No, let me fix it
      </BigButton>

      <button type="button" onClick={() => void openOutputFolder()}>
        📂 See all my finished books
      </button>
    </main>
  );
}
