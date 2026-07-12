import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { pickFolder, updateSettings } from "../api/client";

export interface FoldersScreenProps {
  booksFolder: string;
  outputFolder: string;
  onDone: () => void;
}

/** First-launch one-time setup, and the "⚙️ Change my folders" settings
 * entry point later -- the same screen either way
 * (03-gui-ux-design.md §First launch only: one-time setup, §Settings
 * areas §Change my folders), the only difference being whether a
 * folder already has a value to show next to its button.
 */
export function FoldersScreen({ booksFolder, outputFolder, onDone }: FoldersScreenProps) {
  const [books, setBooks] = useState(booksFolder);
  const [output, setOutput] = useState(outputFolder);
  const [saving, setSaving] = useState(false);

  async function chooseBooksFolder() {
    const result = await pickFolder({
      title: "Where are your book files?",
      initialDir: books,
    });
    if (result.path) setBooks(result.path);
  }

  async function chooseOutputFolder() {
    const result = await pickFolder({
      title: "Where should your finished books go?",
      initialDir: output,
    });
    if (result.path) setOutput(result.path);
  }

  async function handleDone() {
    setSaving(true);
    try {
      await updateSettings({ books_folder: books, output_folder: output });
      onDone();
    } finally {
      setSaving(false);
    }
  }

  const canFinish = books.trim() !== "" && output.trim() !== "" && !saving;

  return (
    <main aria-labelledby="folders-heading">
      <h1 id="folders-heading">Your folders</h1>
      <div className="field">
        <p>Where are your book files?</p>
        <BigButton
          variant="plain"
          aria-label="Choose folder for your book files"
          onClick={() => void chooseBooksFolder()}
        >
          Choose Folder...
        </BigButton>
        {books ? <p className="caption">Currently: {books}</p> : null}
      </div>
      <div className="field">
        <p>Where should your finished books go?</p>
        <BigButton
          variant="plain"
          aria-label="Choose folder for your finished books"
          onClick={() => void chooseOutputFolder()}
        >
          Choose Folder...
        </BigButton>
        {output ? <p className="caption">Currently: {output}</p> : null}
      </div>
      <BigButton variant="primary" onClick={() => void handleDone()} disabled={!canFinish}>
        Done
      </BigButton>
    </main>
  );
}
