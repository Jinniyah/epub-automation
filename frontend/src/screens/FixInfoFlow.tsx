import { useState } from "react";
import { FieldCorrectionPopup } from "../components/shared/FieldCorrectionPopup";
import { BigButton } from "../components/shared/BigButton";
import { openBookFolder, retagBook } from "../api/client";
import type { Book, MetadataCorrections } from "../api/types";
import { formatAuthor, parseAuthor } from "../utils/authorName";

export interface FixInfoFlowProps {
  book: Book;
  onDone: () => void;
  onCancel: () => void;
}

type FieldStep = "author" | "title" | "series" | "series_number";
type Phase = "editing" | "fixing" | "fixed";

const LABELS: Record<FieldStep, string> = {
  author: "Author",
  title: "Title",
  series: "Series",
  series_number: "Series Number",
};

/** "No, let me fix it" (03-gui-ux-design.md) -- reuses the exact same
 * Field Correction Popup as the pre-generation confirm step, stepping
 * through Author, Title, and (only for a book that has one) Series and
 * Series Number, then a fast local retag pass -- no audio is
 * regenerated.
 */
export function FixInfoFlow({ book, onDone, onCancel }: FixInfoFlowProps) {
  const steps: FieldStep[] = book.series
    ? ["author", "title", "series", "series_number"]
    : ["author", "title"];
  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState<Record<FieldStep, string>>({
    author: formatAuthor(book.author_first, book.author_last),
    title: book.title ?? "",
    series: book.series ?? "",
    series_number: book.series_number ?? "",
  });
  const [phase, setPhase] = useState<Phase>("editing");
  const [folderError, setFolderError] = useState<string | null>(null);

  const currentStep = steps[stepIndex];

  async function submitRetag(finalValues: Record<FieldStep, string>) {
    setPhase("fixing");
    const parsedAuthor = parseAuthor(finalValues.author);
    const overrides: MetadataCorrections = {
      title: finalValues.title,
      author_first: parsedAuthor.author_first,
      author_last: parsedAuthor.author_last,
    };
    if (book.series) {
      overrides.series = finalValues.series;
      overrides.series_number = finalValues.series_number;
    }
    await retagBook(book.id, overrides);
    setPhase("fixed");
  }

  function handleSave(value: string) {
    const nextValues = { ...values, [currentStep]: value };
    setValues(nextValues);
    if (stepIndex + 1 < steps.length) {
      setStepIndex(stepIndex + 1);
    } else {
      void submitRetag(nextValues);
    }
  }

  async function openFolder() {
    const result = await openBookFolder(book.id);
    setFolderError(result.ok ? null : "We couldn't open that folder.");
  }

  if (phase === "fixing") {
    return (
      <main aria-labelledby="fixing-heading">
        <h1 id="fixing-heading">🔄 Fixing {book.title ?? "the"} files now...</h1>
      </main>
    );
  }

  if (phase === "fixed") {
    return (
      <main aria-labelledby="fixed-heading">
        <h1 id="fixed-heading">✅ Fixed!</h1>
        <button type="button" onClick={() => void openFolder()}>
          📂 See the audiobook files
        </button>
        {folderError ? <p role="alert">{folderError}</p> : null}
        <BigButton variant="primary" onClick={onDone}>
          Done
        </BigButton>
      </main>
    );
  }

  return (
    <main aria-labelledby="fixit-heading">
      <h1 id="fixit-heading">Let's fix {book.title ?? "this book"}'s info.</h1>
      <FieldCorrectionPopup
        key={currentStep}
        fieldLabel={LABELS[currentStep]}
        initialValue={values[currentStep]}
        saveLabel="Next"
        onClose={onCancel}
        onSave={handleSave}
      />
    </main>
  );
}
