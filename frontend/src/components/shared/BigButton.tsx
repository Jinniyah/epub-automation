import { useId, type ButtonHTMLAttributes, type ReactNode } from "react";

export type BigButtonVariant = "primary" | "amber" | "danger" | "plain";

export interface BigButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BigButtonVariant;
  /** Permanent caption text under the button -- never a hover tooltip
   * (03-gui-ux-design.md §General principles: "no hover-to-reveal").
   * Wired via aria-describedby so a screen-reader user gets the same
   * explanation as part of the button's accessible description. */
  caption?: ReactNode;
  children: ReactNode;
}

/** A big click target (>=70px tall, docs/requirements/03-gui-ux-design.md
 * §General principles), used for every primary action across the app.
 */
export function BigButton({
  variant = "primary",
  caption,
  children,
  className,
  ...rest
}: BigButtonProps) {
  const captionId = useId();
  return (
    <div className="big-button-wrap">
      <button
        type="button"
        className={["big-button", `big-button--${variant}`, className]
          .filter(Boolean)
          .join(" ")}
        aria-describedby={caption ? captionId : undefined}
        {...rest}
      >
        {children}
      </button>
      {caption ? (
        <p className="caption" id={captionId}>
          {caption}
        </p>
      ) : null}
    </div>
  );
}
