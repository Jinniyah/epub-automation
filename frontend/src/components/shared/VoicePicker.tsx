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
  /** Puts the Next button in a `.screen-actions` sticky bottom bar
   * (docs/BACKLOG.md Epic 8.6). Opt-in and off by default: this
   * component is reused inside an `Overlay` for the "Change Voice"
   * popup, where a sticky-positioned bar would be the wrong fit (see
   * `.screen-actions`' own doc comment in index.css) -- only the
   * single-book full-screen usage should pass this. */
  stickyActions?: boolean;
  onNext: (voice: string) => void;
}

/** The full voice-picker list (03-gui-ux-design.md §Voice assignment) --
 * used both as the single-book full screen and, wrapped in an
 * `Overlay`, as the multi-book table's "Change Voice" popup. Plain
 * first names only, radio rows with an independent Listen action per
 * row (RadioRow already implements both the RA-friendly big-row target
 * and the WCAG keyboard/labelling requirements this needs).
 *
 * **Spacing (fixed 2026-07-17, real screenshot + follow-up request):**
 * the heading and the row list used to sit directly adjacent with zero
 * gap -- `main > * + *`'s app-wide section rhythm never reached them,
 * since they're grandchildren of `main` here (children of this
 * component's own wrapping `<div>`, which is `main`'s one child), not
 * direct children of `main` itself. Fixed with the new `.stack`
 * utility (index.css) for the heading -> list gap, and `.stack-md` for
 * gaps between individual rows (real feedback: touching rows read as
 * one crowded block). The rows' own 70px `min-height` is deliberately
 * unchanged despite the added scroll -- that's the app-wide
 * accessibility floor for the RA persona (03-gui-ux-design.md §General
 * principles), not incidental sizing, and shrinking it would work
 * against the same real-user population this spacing fix is for.
 */
export function VoicePicker({
  bookLabel,
  initialVoice,
  lastUsedVoice,
  voices: providedVoices,
  stickyActions = false,
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

  const nextButton = (
    <BigButton
      variant="primary"
      disabled={voices === null}
      onClick={() => onNext(voice)}
    >
      Next
    </BigButton>
  );

  return (
    <div>
      <div className="stack">
        <h2>🎙️ Pick a voice for {bookLabel}</h2>
        {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a short
            spoken voice sample, not a video/dialogue track. */}
        <audio ref={audioRef} className="sr-only" />
        {voices === null ? (
          <p>Getting voice samples ready...</p>
        ) : (
          <div
            role="radiogroup"
            className="stack-md"
            aria-label={`Voice for ${bookLabel}`}
          >
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
      </div>
      {stickyActions ? <div className="screen-actions">{nextButton}</div> : nextButton}
    </div>
  );
}
