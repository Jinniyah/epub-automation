import type { ReactNode } from "react";

export interface RadioRowAction {
  /** Real accessible name for the nested action, e.g. "Play preview:
   * George" -- never just a bare glyph (03-gui-ux-design.md §Perceivable:
   * "Voice preview buttons have real accessible names"). */
  label: string;
  onClick: () => void;
  icon?: ReactNode;
}

export interface RadioRowProps {
  name: string;
  value: string;
  checked: boolean;
  onSelect: (value: string) => void;
  label: string;
  /** e.g. "last used" -- rendered as a caption, never color-only. */
  badge?: string;
  /** A distinct nested target within the row (the voice picker's
   * ▶ Listen button) -- tapping it must not also select the row
   * (03-gui-ux-design.md §Voice assignment). Both the row and this
   * action are independently keyboard-reachable. */
  action?: RadioRowAction;
}

/** The fully-clickable radio-row pattern used everywhere a big single-
 * choice list appears (voice picker, AI Helper Setup) --
 * 03-gui-ux-design.md §General principles: "the whole row ... selects
 * the option," and §Operable: "a real, keyboard-focusable,
 * Enter/Space-activatable control." A native `<input type="radio">`
 * wrapped in its `<label>` gets all of that for free -- Tab/Space/Enter,
 * arrow-key movement within the group, and a real accessible name -- so
 * there's no hand-rolled key handling to get wrong.
 */
export function RadioRow({
  name,
  value,
  checked,
  onSelect,
  label,
  badge,
  action,
}: RadioRowProps) {
  return (
    <label
      className={"clickable-row" + (checked ? " clickable-row--checked" : "")}
    >
      <input
        type="radio"
        className="sr-only"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
      />
      {/* A real checkmark, not just a color/tint change -- the selected
       * state must never depend on color discrimination alone
       * (03-gui-ux-design.md §Perceivable). Decorative: the native
       * radio's own checked state already carries this for a screen
       * reader. */}
      <span className="clickable-row__check" aria-hidden="true">
        {checked ? "✓" : ""}
      </span>
      <span className="clickable-row__label">
        {label}
        {badge ? <span className="caption"> — {badge}</span> : null}
      </span>
      {action ? (
        <button
          type="button"
          className="clickable-row__action"
          aria-label={action.label}
          onClick={(event) => {
            // A nested interactive control inside a <label> must not
            // also trigger the label's own click-forwarding to the
            // radio input it wraps -- selecting a voice just to preview
            // it would surprise her (03-gui-ux-design.md §Voice
            // assignment: Listen must not also select the row).
            event.preventDefault();
            event.stopPropagation();
            action.onClick();
          }}
        >
          {action.icon}
        </button>
      ) : null}
    </label>
  );
}
