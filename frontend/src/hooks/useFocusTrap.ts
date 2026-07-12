import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function isVisible(el: HTMLElement): boolean {
  // Deliberately not an `offsetParent` check -- that requires a real
  // layout engine (always null under jsdom in tests) and would also
  // wrongly exclude the .sr-only technique this app uses on purpose
  // (RadioRow's native radio input): visually clipped but genuinely
  // still part of the layout, not display:none/visibility:hidden.
  if (el.hidden) return false;
  const style = window.getComputedStyle(el);
  return style.display !== "none" && style.visibility !== "hidden";
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter(isVisible);
}

export interface UseFocusTrapOptions {
  /** Whether the overlay is currently open. */
  active: boolean;
  /** Called when Escape is pressed -- equivalent to the visible close/
   * cancel control (03-gui-ux-design.md §Operable). */
  onClose: () => void;
}

/** Traps Tab/Shift+Tab inside the returned container ref while `active`,
 * moves focus into it on open, and returns focus to whatever element had
 * focus before opening once it closes -- every overlay (Field Correction
 * Popup, voice picker, AI Helper Setup) needs exactly this behavior
 * (03-gui-ux-design.md §Operable, docs/design/PATTERNS.md §2).
 */
export function useFocusTrap<T extends HTMLElement>({
  active,
  onClose,
}: UseFocusTrapOptions): React.RefObject<T | null> {
  const containerRef = useRef<T>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const container = containerRef.current;
    if (container) {
      const focusable = focusableElements(container);
      (focusable[0] ?? container).focus();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !container) return;

      const focusable = focusableElements(container);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocusedRef.current?.focus();
    };
  }, [active, onClose]);

  return containerRef;
}
