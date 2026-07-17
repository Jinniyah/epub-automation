import { BigButton } from "../components/shared/BigButton";

export interface MoreOptionsScreenProps {
  onOpenFolders: () => void;
  onOpenWords: () => void;
  onOpenAiHelper: () => void;
  onOpenVoiceHistory: () => void;
  onDone: () => void;
}

/** "More options" hub (03-gui-ux-design.md §Settings areas) -- reached
 * from Screen 1's single "⚙️ More options" entry point. Previously these
 * four destinations were four separate small link-style buttons directly
 * on Screen 1; real feedback (vision + fine-motor-control difficulty)
 * flagged them as too small and too easy to miss/mis-tap. Consolidating
 * to one entry point keeps Screen 1 itself down to its two real
 * decisions (which books, then Start) per §General principles' "one
 * decision per screen," while every option here gets the same full
 * ~70px big-click-target treatment as everywhere else in the app --
 * solving the sizing complaint without cluttering Screen 1 with four
 * more big buttons stacked above Start.
 */
export function MoreOptionsScreen({
  onOpenFolders,
  onOpenWords,
  onOpenAiHelper,
  onOpenVoiceHistory,
  onDone,
}: MoreOptionsScreenProps) {
  return (
    <main aria-labelledby="more-options-heading">
      <h1 id="more-options-heading">More options</h1>

      <div className="option-stack">
        <BigButton variant="plain" onClick={onOpenFolders}>
          ⚙️ Change my folders
        </BigButton>
        <BigButton variant="plain" onClick={onOpenWords}>
          🧼 Words to clean up
        </BigButton>
        <BigButton variant="plain" onClick={onOpenAiHelper}>
          🤖 File name helper
        </BigButton>
        <BigButton variant="plain" onClick={onOpenVoiceHistory}>
          🎙️ What voice did I use before?
        </BigButton>
      </div>

      <BigButton variant="primary" onClick={onDone}>
        Done
      </BigButton>
    </main>
  );
}
