import { useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { LiveRegion } from "../components/shared/LiveRegion";
import { requestSupportBundle } from "../api/client";

export interface ErrorScreenProps {
  summary: string;
  onBackToStart: () => void;
}

/** The generic "Something went wrong" screen
 * (06-safety-error-handling.md §Error communication) -- `summary` is
 * always the friendly, non-technical message the backend already
 * chose; the real technical detail only ever leaves the machine via
 * "Copy details for support," never over the polling response.
 */
export function ErrorScreen({ summary, onBackToStart }: ErrorScreenProps) {
  const [bundlePath, setBundlePath] = useState<string | null>(null);

  async function copyDetails() {
    const result = await requestSupportBundle();
    setBundlePath(result.path);
  }

  return (
    <main aria-labelledby="error-heading">
      <h1 id="error-heading">Something went wrong</h1>
      <LiveRegion politeness="assertive">{summary}</LiveRegion>
      <BigButton variant="plain" onClick={() => void copyDetails()}>
        Copy details for support
      </BigButton>
      {bundlePath ? <p className="caption">Saved to: {bundlePath}</p> : null}
      <BigButton variant="primary" onClick={onBackToStart}>
        Back to Add Books
      </BigButton>
    </main>
  );
}
