import { useEffect, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { EditableFieldRow } from "../components/shared/EditableFieldRow";
import { FieldCorrectionPopup } from "../components/shared/FieldCorrectionPopup";
import { RemoveBookButton } from "../components/shared/RemoveBookButton";
import { StepProgress } from "../components/shared/StepProgress";
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
  /** Only offered outside `asOverlay` mode -- a book reopened from the
   * voice table is already past this step for the rest of the batch;
   * removing it there belongs to the table's own row action instead.
   * Not one of the original 8 feedback items -- surfaced when a real
   * run hit a book stuck here with no way out but to fill in fake data
   * (docs/BACKLOG.md Epic 8.5). */
  onRemoved?: () => void;
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
 *
 * **Visual design system (docs/BACKLOG.md Epic 8.6):** in standalone
 * mode, the field list is its own `.card` and the primary action sits
 * in a `.screen-actions` sticky bottom bar. Neither applies in
 * `asOverlay` mode -- the enclosing `Overlay` already provides its own
 * bounded card surface and its own action area, so nesting either
 * pattern again here would double up rather than add clarity, and a
 * sticky-positioned bar specifically risks colliding with the
 * overlay's own focus trap (see `.screen-actions`' own doc comment in
 * index.css).
 *
 * **Overlay-mode spacing (fixed 2026-07-17, real screenshot):** in
 * `asOverlay` mode, this whole component renders as a single wrapping
 * `<div>` -- the sole `children` of `Overlay`, which sits alongside
 * `Overlay`'s own `<h2>` title as `.overlay`'s two direct children.
 * `.overlay`'s own `> * + *` rhythm (index.css, space-4) reaches that
 * gap fine, but the field list and the Save button are *this*
 * component's own two children, one level deeper -- the same
 * `main > * + *`-doesn't-reach-grandchildren gap `VoicePicker` had
 * (docs/BACKLOG.md Epic 8.5), just one level further down. Fixed by
 * wrapping them in `.stack` (index.css) for `asOverlay` mode only.
 * **Deliberately not solved by flattening this component's wrapper
 * into a `Fragment`** (the seemingly cleaner fix, letting `.overlay`'s
 * own rule reach fieldList/confirmButton directly): the conditionally-
 * rendered `FieldCorrectionPopup` blocks below are themselves full
 * `Overlay`s (`position: fixed` backdrop) -- flattening would make one
 * a DOM sibling of fieldList/confirmButton at the same level, and
 * `.overlay > * + *` would then apply an unwanted `margin-top` to that
 * fixed-position backdrop, visibly shifting the popup-on-a-popup down
 * from the screen edge it's meant to fully cover.
 */
export function ConfirmMetadataScreen({
  book,
  enrichmentFailed = false,
  onConfirmed,
  onRemoved,
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

  const fieldList = (
    <div className="stack-sm">
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
    </div>
  );

  const confirmButton = (
    <BigButton variant="primary" disabled={saving} onClick={() => void handleConfirm()}>
      {asOverlay ? "Save" : "Looks good"}
    </BigButton>
  );

  return (
    <Wrapper aria-labelledby={asOverlay ? undefined : "confirm-heading"}>
      {asOverlay ? null : (
        <>
          <h1 id="confirm-heading">{heading}</h1>
          <StepProgress
            current="confirm_info"
            activeBookTitle={title || book.original_filename}
          />
        </>
      )}

      {asOverlay ? (
        <div className="stack">
          {fieldList}
          {confirmButton}
        </div>
      ) : (
        <>
          <div className="card">{fieldList}</div>
          <div className="screen-actions stack-sm">
            {confirmButton}
            {onRemoved ? (
              <RemoveBookButton
                bookId={book.id}
                bookLabel={title || book.original_filename}
                onRemoved={onRemoved}
              />
            ) : null}
          </div>
        </>
      )}

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
          hint="Last name, first name -- like Jacka, Benedict"
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
          hint="Just the number -- like 1 or 2.5"
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
