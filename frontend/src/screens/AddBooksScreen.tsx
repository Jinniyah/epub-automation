import { useCallback, useEffect, useRef, useState } from "react";
import type { DragEvent } from "react";
import { BigButton } from "../components/shared/BigButton";
import { LiveRegion } from "../components/shared/LiveRegion";
import { ToggleSwitch } from "../components/shared/ToggleSwitch";
import { addBooks, getDiskSpace, removeBook, startBatch, updateSettings } from "../api/client";
import type { Book, DiskSpaceReport } from "../api/types";

export interface AddBooksScreenProps {
  books: Book[];
  fixNames: boolean;
  cleanLanguage: boolean;
  /** Re-poll status immediately after a mutation (add/remove/toggle),
   * rather than waiting for the next regular tick. */
  onChanged: () => void;
  onStart: () => void;
  onOpenFolders: () => void;
  onOpenWords: () => void;
  onOpenAiHelper: () => void;
  onOpenVoiceHistory: () => void;
}

interface Rejection {
  filename: string;
  message: string;
}

/** Screen 1: Add Books (03-gui-ux-design.md). Drag-and-drop is
 * supported but never the only way in -- "Choose Books..." is an
 * equally capable native file picker, since drag-and-drop needs more
 * precise motor control (RA) and isn't operable via keyboard or screen
 * reader at all (§Operable).
 */
export function AddBooksScreen({
  books,
  fixNames,
  cleanLanguage,
  onChanged,
  onStart,
  onOpenFolders,
  onOpenWords,
  onOpenAiHelper,
  onOpenVoiceHistory,
}: AddBooksScreenProps) {
  const [rejections, setRejections] = useState<Rejection[]>([]);
  const [diskSpace, setDiskSpace] = useState<DiskSpaceReport | null>(null);
  const [starting, setStarting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshDiskSpace = useCallback(async () => {
    if (books.length === 0) {
      setDiskSpace(null);
      return;
    }
    setDiskSpace(await getDiskSpace());
  }, [books.length]);

  useEffect(() => {
    void refreshDiskSpace();
  }, [refreshDiskSpace]);

  async function handleFiles(files: FileList | File[]) {
    const list = Array.from(files);
    if (list.length === 0) return;
    const response = await addBooks(list);
    setRejections(
      response.results
        .filter((r) => !r.ok)
        .map((r) => ({
          filename: r.original_filename,
          message: r.message ?? "That file couldn't be added.",
        })),
    );
    onChanged();
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    void handleFiles(event.dataTransfer.files);
  }

  async function handleRemove(bookId: string) {
    await removeBook(bookId);
    onChanged();
  }

  async function handleStart() {
    setStarting(true);
    try {
      await startBatch();
      onStart();
    } finally {
      setStarting(false);
    }
  }

  return (
    <main aria-labelledby="add-books-heading">
      <h1 id="add-books-heading">Add your books</h1>

      <div
        className="dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        <p>📚 Drop your book files here, or</p>
        <BigButton variant="plain" onClick={() => fileInputRef.current?.click()}>
          Choose Books...
        </BigButton>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".epub"
          aria-label="Choose book files"
          className="sr-only"
          onChange={(event) => {
            if (event.target.files) void handleFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {rejections.length > 0 ? (
        <LiveRegion politeness="assertive">
          <ul className="row-list">
            {rejections.map((r) => (
              <li key={r.filename} className="row-list__item">
                {r.filename}: {r.message}
              </li>
            ))}
          </ul>
        </LiveRegion>
      ) : null}

      <div>
        <h2>Your books</h2>
        {books.length === 0 ? (
          <p className="caption">No books added yet.</p>
        ) : (
          <ul className="row-list">
            {books.map((book) => (
              <li key={book.id} className="row-list__item">
                <span className="row-list__label">
                  <span aria-hidden="true">✓</span> {book.original_filename}
                </span>
                <button
                  type="button"
                  className="link-button link-button--danger"
                  aria-label={`Remove "${book.original_filename}"`}
                  onClick={() => void handleRemove(book.id)}
                >
                  ✕ Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {diskSpace?.any_insufficient ? (
        <LiveRegion politeness="assertive">
          You might not have enough space on your computer for all these books
          yet. You can still try, or remove a few first.
        </LiveRegion>
      ) : null}

      <div className="stack-sm">
        <ToggleSwitch
          label="🏷️ Fix messy file names"
          checked={fixNames}
          onChange={(checked) => {
            void updateSettings({ fix_names: checked }).then(onChanged);
          }}
        />
        <ToggleSwitch
          label="🧼 Clean up bad language"
          checked={cleanLanguage}
          onChange={(checked) => {
            void updateSettings({ clean_language: checked }).then(onChanged);
          }}
        />
      </div>

      <nav aria-label="More options" className="entry-points">
        <button type="button" className="link-button" onClick={onOpenFolders}>
          ⚙️ Change my folders
        </button>
        <button type="button" className="link-button" onClick={onOpenWords}>
          🧼 Words to clean up
        </button>
        <button type="button" className="link-button" onClick={onOpenAiHelper}>
          🤖 File name helper
        </button>
        <button type="button" className="link-button" onClick={onOpenVoiceHistory}>
          🎙️ What voice did I use before?
        </button>
      </nav>

      <BigButton
        variant="primary"
        disabled={books.length === 0 || starting}
        onClick={() => void handleStart()}
      >
        Start
      </BigButton>
    </main>
  );
}
