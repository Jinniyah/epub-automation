import { useEffect, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { Overlay } from "../components/shared/Overlay";
import { VoicePicker } from "../components/shared/VoicePicker";
import { assignVoice, getVoices, startGeneration } from "../api/client";
import type { Book, VoiceChoice } from "../api/types";
import { useVoiceAssignmentView } from "../viewmodels/useVoiceAssignmentView";
import { ConfirmMetadataScreen } from "./ConfirmMetadataScreen";

export interface VoiceAssignmentScreenProps {
  books: Book[];
  lastVoice?: string;
  onChanged: () => void;
}

function voiceDisplayName(voices: VoiceChoice[] | null, key: string): string {
  return voices?.find((v) => v.key === key)?.name ?? key;
}

/** §Voice assignment (03-gui-ux-design.md) -- single-book full picker or
 * the multi-book table, chosen by `useVoiceAssignmentView`'s `mode`.
 */
export function VoiceAssignmentScreen({
  books,
  lastVoice,
  onChanged,
}: VoiceAssignmentScreenProps) {
  const { mode, rows } = useVoiceAssignmentView(books);
  const [voices, setVoices] = useState<VoiceChoice[] | null>(null);
  const [changingVoiceFor, setChangingVoiceFor] = useState<string | null>(null);
  const [editingMetadataFor, setEditingMetadataFor] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    void getVoices().then((response) => setVoices(response.voices));
  }, []);

  async function handleAssign(bookId: string, voice: string) {
    await assignVoice(bookId, voice);
    setChangingVoiceFor(null);
    onChanged();
  }

  if (mode === "single") {
    const row = rows[0];
    const label = row.series ? `"${row.title}" (${row.series})` : `"${row.title}"`;
    return (
      <main aria-labelledby="voice-single-heading">
        <h1 id="voice-single-heading" className="sr-only">
          Pick a voice
        </h1>
        <VoicePicker
          bookLabel={label}
          initialVoice={row.voice}
          lastUsedVoice={lastVoice}
          voices={voices}
          onNext={(voice) => void handleAssign(row.bookId, voice)}
        />
      </main>
    );
  }

  const changingRow = rows.find((r) => r.bookId === changingVoiceFor);
  const editingRow = rows.find((r) => r.bookId === editingMetadataFor);

  return (
    <main aria-labelledby="voice-table-heading">
      <h1 id="voice-table-heading">🎙️ Choose a voice for each book</h1>
      <table>
        <caption className="sr-only">Voice for each book in this batch</caption>
        <thead>
          <tr>
            <th scope="col">Book</th>
            <th scope="col">Voice</th>
            <th scope="col">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.bookId}>
              <td>
                <button type="button" onClick={() => setEditingMetadataFor(row.bookId)}>
                  📖 {row.title}
                  {row.author ? ` — ${row.author}` : ""}
                  {row.series ? ` — ${row.series}` : ""}
                </button>
              </td>
              <td>{voiceDisplayName(voices, row.voice)}</td>
              <td>
                <button type="button" onClick={() => setChangingVoiceFor(row.bookId)}>
                  Change Voice
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <BigButton
        variant="primary"
        disabled={starting}
        onClick={() => {
          setStarting(true);
          void startGeneration().then(() => {
            setStarting(false);
            onChanged();
          });
        }}
      >
        Start All Books
      </BigButton>

      {changingRow ? (
        <Overlay
          titleId="change-voice-heading"
          title={`Change voice for "${changingRow.title}"`}
          onClose={() => setChangingVoiceFor(null)}
        >
          <VoicePicker
            bookLabel={`"${changingRow.title}"`}
            initialVoice={changingRow.voice}
            lastUsedVoice={lastVoice}
            voices={voices}
            onNext={(voice) => void handleAssign(changingRow.bookId, voice)}
          />
        </Overlay>
      ) : null}

      {editingRow ? (
        <Overlay
          titleId="edit-metadata-heading"
          title={`Update "${editingRow.title}"'s info`}
          onClose={() => setEditingMetadataFor(null)}
        >
          <ConfirmMetadataScreen
            asOverlay
            book={books.find((b) => b.id === editingRow.bookId)!}
            onConfirmed={() => {
              setEditingMetadataFor(null);
              onChanged();
            }}
          />
        </Overlay>
      ) : null}
    </main>
  );
}
