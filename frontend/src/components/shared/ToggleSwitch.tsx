export interface ToggleSwitchProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/** A big toggle switch, never a small checkbox
 * (03-gui-ux-design.md §General principles) -- Screen 1's "Fix messy
 * file names" / "Clean up bad language" toggles. The On/Off text is
 * real visible content (not decorative), so it's part of the row's
 * accessible name the same way a sighted user reads it, on top of the
 * native checkbox's own checked/unchecked state.
 */
export function ToggleSwitch({ label, checked, onChange }: ToggleSwitchProps) {
  return (
    <label className={"clickable-row" + (checked ? " clickable-row--checked" : "")}>
      <input
        type="checkbox"
        className="sr-only"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
      <span>{checked ? "On" : "Off"}</span>
    </label>
  );
}
