import { useId } from "react";

export type Step = "add_books" | "confirm_info" | "choose_voice" | "convert" | "review";

export interface StepProgressProps {
  current: Step;
  /** Whichever book is currently active for this step, if any --
   * "Add Books" is batch-wide by nature and never sets this
   * (docs/BACKLOG.md Epic 9). Rendered as its own line below the step
   * row, tied to the `<nav>` via `aria-describedby` rather than inlined
   * into the step label itself, so a screen-reader user gets both facts
   * together without the step wording changing length book to book. */
  activeBookTitle?: string;
}

const STEPS: { key: Step; label: string }[] = [
  { key: "add_books", label: "Add Books" },
  { key: "confirm_info", label: "Confirm Info" },
  { key: "choose_voice", label: "Choose Voice" },
  { key: "convert", label: "Convert" },
  { key: "review", label: "Review" },
];

/** Persistent "you are here" step indicator across the main batch flow
 * (docs/BACKLOG.md Epic 9, real user feedback: no orientation cue for a
 * first-time/FMS-persona user). Rendered by each of the five main-flow
 * screens themselves, right after their own `<h1>` -- deliberately not
 * by `App.tsx`, since each screen already has (or trivially computes)
 * its own notion of "active book" without needing that state lifted up.
 *
 * Current/completed state is never color-only (03-gui-ux-design.md
 * §Perceivable, the same rule already applied to
 * `.clickable-row--checked`): a completed step's marker is a checkmark
 * glyph (a shape change), the current step's marker is filled with its
 * number and its label is bold + underlined, an upcoming step's marker
 * is unfilled/outlined -- every pair of states differs by more than
 * color alone.
 */
export function StepProgress({ current, activeBookTitle }: StepProgressProps) {
  const bookTitleId = useId();
  const currentIndex = STEPS.findIndex((step) => step.key === current);

  return (
    <div className="step-progress">
      <nav
        aria-label="Progress"
        aria-describedby={activeBookTitle ? bookTitleId : undefined}
      >
        <ol className="step-progress__list">
          {STEPS.map((step, index) => {
            const isCurrent = step.key === current;
            const isComplete = index < currentIndex;
            return (
              <li
                key={step.key}
                className={[
                  "step-progress__item",
                  isCurrent ? "step-progress__item--current" : "",
                  isComplete ? "step-progress__item--complete" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={isCurrent ? "step" : undefined}
              >
                <span className="step-progress__marker" aria-hidden="true">
                  {isComplete ? "✓" : index + 1}
                </span>
                <span className="step-progress__label">{step.label}</span>
              </li>
            );
          })}
        </ol>
      </nav>
      {activeBookTitle ? (
        <p id={bookTitleId} className="step-progress__book">
          📖 {activeBookTitle}
        </p>
      ) : null}
    </div>
  );
}
