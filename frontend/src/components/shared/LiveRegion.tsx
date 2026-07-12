import type { ReactNode } from "react";

export interface LiveRegionProps {
  politeness: "polite" | "assertive";
  children: ReactNode;
  className?: string;
}

/** A visible status/error region that's also announced to a screen
 * reader (03-gui-ux-design.md §Status updates for screen-reader users):
 * `message` uses "polite" (announced without interrupting), `error`
 * uses "assertive" (interrupts immediately). Always render the actual
 * text a sighted user sees here -- throttle *what* text arrives via
 * `useAriaLiveThrottled`, not by hiding this region.
 */
export function LiveRegion({ politeness, children, className }: LiveRegionProps) {
  return (
    <div
      role={politeness === "assertive" ? "alert" : "status"}
      aria-live={politeness}
      className={className}
    >
      {children}
    </div>
  );
}
