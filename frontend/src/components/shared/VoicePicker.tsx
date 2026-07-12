import { useEffect, useRef, useState } from "react";
import { BigButton } from "./BigButton";
import { RadioRow } from "./RadioRow";
import { getVoices, voiceSampleUrl } from "../../api/client";
import type { VoiceChoice } from "../../api/types";

export interface VoicePickerProps {
  /** e.g. `"Fated" (Alex Verus #1)` -- already formatted by the caller. */
  bookLabel: string;
  initialVoice: string;
  lastUsedVoice?: string;
  /** Preloaded voice list, e.g. from a container that already fetched it
   * once for a whole table of rows -- skips this component's own fetch
   * (and the lazy sample-cache trigger that comes with it) when given. */
  voices?: VoiceChoice[] | null;
  onNext: (voice: string) => void;
}

/** The full voice-picker list (03-gui-ux-design.md §Voice assignment) --
 * used both as the single-book full screen and, wrapped in an
 * `Overlay`, as the multi-book table's "Change Voice" popup. Plain
 * first names only, radio rows with an independent Listen action per
 * row (RadioRow already implements both the RA-friendly big-row target
 * and the WCAG keyboard/labelling requirements this needs).
 */
export function VoicePicker({
  bookLabel,
  initialVoice,
  lastUsedVoice,
  voices: providedVoices,
  onNext,
}: VoicePickerProps) {
  const [voices, setVoices] = useState<VoiceChoice[] | null>(providedVoices ?? null);
  const [voice, setVoice] = useState(initialVoice);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (providedVoices !== undefined) {
      setVoices(providedVoices);
      return;
    }
    let cancelled = false;
    void getVoices().then((response) => {
      if (!cancelled) setVoices(response.voices);
    });
    return () => {
      cancelled = true;
    };
  }, [providedVoices]);

  function playPreview(key: string) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.src = voiceSampleUrl(key);
    void audio.play();
  }

  return (
    <div>
      <h2>🎙️ Pick a voice for {bookLabel}</h2>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a short
          spoken voice sample, not a video/dialogue track. */}
      <audio ref={audioRef} className="sr-only" />
      {voices === null ? (
        <p>Getting voice samples ready...</p>
      ) : (
        <div role="radiogroup" aria-label={`Voice for ${bookLabel}`}>
          {voices.map((v) => (
            <RadioRow
              key={v.key}
              name="voice-pick"
              value={v.key}
              checked={voice === v.key}
              onSelect={setVoice}
              label={v.name}
              badge={[v.gender, v.key === lastUsedVoice ? "last used" : null]
                .filter(Boolean)
                .join(", ")}
              action={{
                label: `Play preview: ${v.name}`,
                icon: <span aria-hidden="true">▶ Listen</span>,
                onClick: () => playPreview(v.key),
              }}
            />
          ))}
        </div>
      )}
      <BigButton
        variant="primary"
        disabled={voices === null}
        onClick={() => onNext(voice)}
      >
        Next
      </BigButton>
    </div>
  );
}
