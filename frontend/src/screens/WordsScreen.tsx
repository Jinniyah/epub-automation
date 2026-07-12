import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { updateSettings } from "../api/client";

export interface WordsScreenProps {
  words: string[];
  onDone: () => void;
}

/** "Words to clean up" (03-gui-ux-design.md §Settings areas) -- one word
 * at a time, no multi-select, no inline editing (remove and re-add to
 * fix a typo). Always fetch-then-send the whole array back
 * (01-architecture.md's own note on this route).
 */
export function WordsScreen({ words: initialWords, onDone }: WordsScreenProps) {
  const [words, setWords] = useState(initialWords);
  const [newWord, setNewWord] = useState("");

  async function persist(nextWords: string[]) {
    setWords(nextWords);
    await updateSettings({ profanity_words: nextWords });
  }

  async function handleRemove(word: string) {
    await persist(words.filter((w) => w !== word));
  }

  async function handleAdd() {
    const trimmed = newWord.trim();
    if (!trimmed) return;
    await persist([...words, trimmed]);
    setNewWord("");
  }

  return (
    <main aria-labelledby="words-heading">
      <h1 id="words-heading">Words to clean up</h1>
      {words.length === 0 ? (
        <p className="caption">No words added yet.</p>
      ) : (
        <ul className="row-list">
          {words.map((word) => (
            <li key={word} className="row-list__item">
              <span className="row-list__label">{word}</span>
              <button
                type="button"
                className="link-button"
                onClick={() => void handleRemove(word)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="inline-form">
        <div className="field">
          <label htmlFor="new-word">Add a new word</label>
          <input
            id="new-word"
            type="text"
            value={newWord}
            onChange={(event) => setNewWord(event.target.value)}
          />
        </div>
        <BigButton
          variant="plain"
          disabled={newWord.trim() === ""}
          onClick={() => void handleAdd()}
        >
          Add
        </BigButton>
      </div>

      <BigButton variant="primary" onClick={onDone}>
        Done
      </BigButton>
    </main>
  );
}
