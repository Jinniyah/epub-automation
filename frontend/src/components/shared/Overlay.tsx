import type { ReactNode } from "react";
import { useFocusTrap } from "../../hooks/useFocusTrap";

export interface OverlayProps {
  titleId: string;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** The large, centered, focus-trapping overlay every popup in this app
 * is built from (Field Correction Popup, the full voice picker, AI
 * Helper Setup's radio screen) -- 03-gui-ux-design.md §Operable: "every
 * overlay traps focus while open" and returns focus to whatever opened
 * it on close; Escape behaves exactly like the visible close control.
 */
export function Overlay({ titleId, title, onClose, children }: OverlayProps) {
  const containerRef = useFocusTrap<HTMLDivElement>({ active: true, onClose });

  return (
    <div className="overlay-backdrop">
      <div
        className="overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={containerRef}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  );
}
