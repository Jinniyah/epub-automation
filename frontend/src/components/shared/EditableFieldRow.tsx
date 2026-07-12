export interface EditableFieldRowProps {
  label: string;
  value: string;
  onEdit: () => void;
}

/** A big, tappable "Label: value" row that opens a `FieldCorrectionPopup`
 * for that field -- used by the per-book metadata review
 * (03-gui-ux-design.md §Per-book identification loop) and the multi-book
 * voice table's clickable title (§Voice assignment).
 */
export function EditableFieldRow({ label, value, onEdit }: EditableFieldRowProps) {
  return (
    <button type="button" className="clickable-row" onClick={onEdit}>
      <span>
        <strong>{label}:</strong> {value || <span className="caption">Not set</span>}
      </span>
      <span aria-hidden="true">✏️</span>
    </button>
  );
}
