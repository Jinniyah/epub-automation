import { useEffect, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { getVoiceHistory, getVoices, requestSupportBundle } from "../api/client";

export interface VoiceHistoryScreenProps {
  onDone: () => void;
}

interface Entry {
  label: string;
  voiceName: string;
}

type LoadState = "loading" | "empty" | "error" | "ready";

/** "What voice did I use before?" (03-gui-ux-design.md §Settings areas)
 * -- read-only. Two distinct empty-looking states worded differently on
 * purpose: legitimately nothing yet vs. the log itself being unreadable
 * -- these must never be conflated.
 */
export function VoiceHistoryScreen({ onDone }: VoiceHistoryScreenProps) {
  const [state, setState] = useState<LoadState>("loading");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [bundlePath, setBundlePath] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const [history, voices] = await Promise.all([getVoiceHistory(), getVoices()]);
      if (!history.ok) {
        setState("error");
        return;
      }
      if (history.history.length === 0) {
        setState("empty");
        return;
      }
      const nameFor = (key: string) =>
        voices.voices.find((v) => v.key === key)?.name ?? key;
      setEntries(history.history.map((h) => ({ label: h.label, voiceName: nameFor(h.voice) })));
      setState("ready");
    })();
  }, []);

  async function copyDetails() {
    const result = await requestSupportBundle();
    setBundlePath(result.path);
  }

  return (
    <main aria-labelledby="voice-history-heading">
      <h1 id="voice-history-heading">🎙️ What voice did I use before?</h1>

      {state === "loading" ? <p>Loading...</p> : null}

      {state === "empty" ? (
        <p>
          You haven't made any audiobooks yet—once you do, you'll be able to check
          what voice you used here.
        </p>
      ) : null}

      {state === "error" ? (
        <>
          <p role="alert">Something went wrong finding your voice history.</p>
          <BigButton variant="plain" onClick={() => void copyDetails()}>
            Copy details for support
          </BigButton>
          {bundlePath ? <p className="caption">Saved to: {bundlePath}</p> : null}
        </>
      ) : null}

      {state === "ready" ? (
        <ul>
          {entries.map((entry) => (
            <li key={entry.label}>
              📖 {entry.label}
              <span>{entry.voiceName}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <BigButton variant="primary" onClick={onDone}>
        Done
      </BigButton>
    </main>
  );
}
