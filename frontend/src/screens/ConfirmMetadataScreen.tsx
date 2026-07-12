import { useEffect, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { EditableFieldRow } from "../components/shared/EditableFieldRow";
import { FieldCorrectionPopup } from "../components/shared/FieldCorrectionPopup";
import { confirmMetadata, updateBookMetadata } from "../api/client";
import type { Book, MetadataCorrections } from "../api/types";
import { formatAuthor, parseAuthor } from "../utils/authorName";

export interface ConfirmMetadataScreenProps {
  book: Book;
  /** True when AI enrichment couldn't fill anything in, so this is
   * asking her to supply it rather than just double-checking it
   * (03-gui-ux-design.md: "no screen shown unless it needs her input --
   * e.g. AI enrichment failed"). Same screen either way, different
   * heading copy. */
  enrichmentFailed?: boolean;
  onConfirmed: () => void;
  /** Renders as plain content (no <main>/<h1>) for reuse inside an
   * `Overlay` -- the multi-book voice table's clickable book title
   * reopens this same review without leaving that screen
   * (03-gui-ux-design.md §Voice assignment). */
  asOverlay?: boolean;
}

type EditableField = "title" | "author" | "series" | "series_number";

/** "Confirm metadata" -- plain-language review of what rename/sanitize
 * found for one book, correctable one field at a time via the shared
 * Field Correction Popup (03-gui-ux-design.md §Per-book identification
 * loop). This loop runs for every book in the batch before voice
 * assignment starts for any of them.
 */
export function ConfirmMetadataScreen({
  book,
  enrichmentFailed = false,
  onConfirmed,
  asOverlay = false,
}: ConfirmMetadataScreenProps) {
  const [title, setTitle] = useState(book.title ?? "");
  const [authorFirst, setAuthorFirst] = useState(book.author_first ?? "");
  const [authorLast, setAuthorLast] = useState(book.author_last ?? "");
  const [series, setSeries] = useState(book.series ?? "");
  const [seriesNumber, setSeriesNumber] = useState(book.series_number ?? "");
  const [editing, setEditing] = useState<EditableField | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setTitle(book.title ?? "");
    setAuthorFirst(book.author_first ?? "");
    setAuthorLast(book.author_last ?? "");
    setSeries(book.series ?? "");
    setSeriesNumber(book.series_number ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the active book itself changes
  }, [book.id]);

  async function handleConfirm() {
    setSaving(true);
    const corrections: MetadataCorrections = {};
    if (title !== (book.title ?? "")) corrections.title = title;
    if (authorFirst !== (book.author_first ?? "")) corrections.author_first = authorFirst;
    if (authorLast !== (book.author_last ?? "")) corrections.author_last = authorLast;
    if (series !== (book.series ?? "")) corrections.series = series;
    if (seriesNumber !== (book.series_number ?? ""))
      corrections.series_number = seriesNumber;
    try {
      if (asOverlay) {
        // Reopened from the voice table: the book is already past
        // `confirm_metadata` (it's sitting at `voice_pick`), so this
        // must patch its metadata directly rather than re-submit the
        // identification loop's own confirm step, which would 409.
        await updateBookMetadata(book.id, corrections);
      } else {
        await confirmMetadata(
          book.id,
          Object.keys(corrections).length > 0 ? corrections : null,
        );
      }
      onConfirmed();
    } finally {
      setSaving(false);
    }
  }

  const Wrapper = asOverlay ? "div" : "main";
  // In overlay mode the enclosing `Overlay` already renders its own
  // <h2> title -- a second heading here would be a duplicate landmark
  // for a screen-reader user, not extra clarity.
  const heading = enrichmentFailed
    ? `We couldn't quite figure out ${title || "this book"} -- can you help?`
    : `Let's check ${title || "this book"}'s info`;

  return (
    <Wrapper aria-labelledby={asOverlay ? undefined : "confirm-heading"}>
      {asOverlay ? null : <h1 id="confirm-heading">{heading}</h1>}
      <EditableFieldRow label="Title" value={title} onEdit={() => setEditing("title")} />
      <EditableFieldRow
        label="Author"
        value={formatAuthor(authorFirst, authorLast)}
        onEdit={() => setEditing("author")}
      />
      <EditableFieldRow
        label="Series"
        value={series}
        onEdit={() => setEditing("series")}
      />
      <EditableFieldRow
        label="Series Number"
        value={seriesNumber}
        onEdit={() => setEditing("series_number")}
      />

      <BigButton variant="primary" disabled={saving} onClick={() => void handleConfirm()}>
        {asOverlay ? "Save" : "Looks good"}
      </BigButton>

      {editing === "title" ? (
        <FieldCorrectionPopup
          fieldLabel="Title"
          initialValue={title}
          onClose={() => setEditing(null)}
          onSave={(value) => {
            setTitle(value);
            setEditing(null);
          }}
        />
      ) : null}
      {editing === "author" ? (
        <FieldCorrectionPopup
          fieldLabel="Author"
          initialValue={formatAuthor(authorFirst, authorLast)}
          onClose={() => setEditing(null)}
          onSave={(value) => {
            const parsed = parseAuthor(value);
            setAuthorFirst(parsed.author_first);
            setAuthorLast(parsed.author_last);
            setEditing(null);
          }}
        />
      ) : null}
      {editing === "series" ? (
        <FieldCorrectionPopup
          fieldLabel="Series"
          initialValue={series}
          onClose={() => setEditing(null)}
          onSave={(value) => {
            setSeries(value);
            setEditing(null);
          }}
        />
      ) : null}
      {editing === "series_number" ? (
        <FieldCorrectionPopup
          fieldLabel="Series Number"
          initialValue={seriesNumber}
          onClose={() => setEditing(null)}
          onSave={(value) => {
            setSeriesNumber(value);
            setEditing(null);
          }}
        />
      ) : null}
    </Wrapper>
  );
}
