import { useEffect, useId, useRef, useState } from "react";
import { Overlay } from "./Overlay";
import { BigButton } from "./BigButton";

export interface FieldCorrectionPopupProps {
  /** e.g. "Author" -- the field's plain-language label. */
  fieldLabel: string;
  initialValue: string;
  onSave: (value: string) => void;
  onClose: () => void;
  /** e.g. "Next" for the "No, let me fix it" flow's step-through
   * (03-gui-ux-design.md's own mockup for that flow) -- same component,
   * same behavior, just a different label for what committing this
   * field actually does next. */
  saveLabel?: string;
  /** Step back to the previous field in a multi-step flow (the
   * identification loop's field-by-field review, "No, let me fix it"),
   * discarding whatever's typed here without saving it. Distinct from
   * `onClose` (Escape/backdrop), which exits the whole flow rather than
   * just stepping back one field -- omitted entirely on the first field
   * of a flow, or when this popup isn't part of a step sequence at all. */
  onBack?: () => void;
}

/** One component, reused identically by the pre-generation "Confirm
 * metadata" step and the post-generation "No, let me fix it" flow
 * (03-gui-ux-design.md §Field Correction Popup) -- never two separate
 * editors. Full-replace, not precise cursor editing: the value opens
 * pre-selected so typing immediately replaces it (no mid-word cursor
 * positioning, RA), and a big Clear button empties it in one tap.
 */
export function FieldCorrectionPopup({
  fieldLabel,
  initialValue,
  onSave,
  onClose,
  saveLabel = "Save",
  onBack,
}: FieldCorrectionPopupProps) {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const inputId = useId();

  useEffect(() => {
    // Runs after Overlay's own focus-trap effect has already focused
    // this input (it's mounted deeper in the tree) -- select-all on top
    // of that focus, so simply typing replaces the whole value.
    inputRef.current?.select();
  }, []);

  return (
    <Overlay titleId={titleId} title={`✏️ ${fieldLabel}`} onClose={onClose}>
      <div className="field">
        <label htmlFor={inputId} className="sr-only">
          {fieldLabel}
        </label>
        <input
          id={inputId}
          ref={inputRef}
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </div>
      {onBack ? (
        <button type="button" className="link-button" onClick={onBack}>
          ← Back
        </button>
      ) : null}
      <div className="overlay-actions">
        <BigButton variant="plain" onClick={() => setValue("")}>
          ✕ Clear
        </BigButton>
        <BigButton variant="primary" onClick={() => onSave(value)}>
          {saveLabel}
        </BigButton>
      </div>
    </Overlay>
  );
}
