import { BigButton } from "../components/shared/BigButton";
import type { CollisionDetail } from "../api/types";

export interface CollisionPromptProps {
  bookTitle: string;
  artifact: CollisionDetail["artifact"];
  onChoice: (choice: "replace" | "keep_both") => void;
}

/** Output collision (06-safety-error-handling.md §Concurrency & duplicate
 * handling) -- distinct prompts per artifact (EPUB vs. audiobook), never
 * a silent skip or overwrite. Not an `Overlay`: this is the current
 * screen itself (blocking, mid-generation, no "cancel" affordance), the
 * same way the identification loop's confirm step isn't dismissible
 * either -- there's nothing to Escape back to.
 */
export function CollisionPrompt({ bookTitle, artifact, onChoice }: CollisionPromptProps) {
  const label = artifact === "audiobook" ? "audiobook" : "book";
  return (
    <main aria-labelledby="collision-heading">
      <h1 id="collision-heading">
        You already have a {label} called "{bookTitle}"
      </h1>
      <p>Want to replace it or keep both?</p>
      <BigButton variant="primary" onClick={() => onChoice("keep_both")}>
        Keep both
      </BigButton>
      <BigButton variant="plain" onClick={() => onChoice("replace")}>
        Replace it
      </BigButton>
    </main>
  );
}
