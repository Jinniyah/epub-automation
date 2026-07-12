import { useId, useState } from "react";
import { BigButton } from "../components/shared/BigButton";
import { RadioRow } from "../components/shared/RadioRow";
import { updateSettings } from "../api/client";
import type { AiProvider } from "../api/types";

export interface AiHelperSetupProps {
  onDone: () => void;
}

type Step = "intro" | "choice" | "key";

const PROVIDER_LABELS: Record<"gemini" | "openai", string> = {
  gemini: "Google (free)",
  openai: "OpenAI",
};

// Each provider's own key-creation page -- "Get a code" opens this in
// her default browser (03-gui-ux-design.md §AI Helper Setup).
const KEY_CREATION_URLS: Record<"gemini" | "openai", string> = {
  gemini: "https://aistudio.google.com/apikey",
  openai: "https://platform.openai.com/api-keys",
};

async function skipToNullProvider(onDone: () => void) {
  await updateSettings({ ai_provider: "none" satisfies AiProvider });
  onDone();
}

/** The one-time, skippable first-launch flow -- also reachable later via
 * "🤖 File name helper" (03-gui-ux-design.md §First launch only: AI
 * Helper Setup). Three steps in one component since they're really one
 * flow: whether to use a helper at all, which one, then its code.
 */
export function AiHelperSetup({ onDone }: AiHelperSetupProps) {
  const [step, setStep] = useState<Step>("intro");
  const [provider, setProvider] = useState<"gemini" | "openai">("gemini");
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const codeInputId = useId();

  if (step === "intro") {
    return (
      <main aria-labelledby="ai-intro-heading">
        <h1 id="ai-intro-heading">
          Want help fixing messy file names automatically?
        </h1>
        <p>This uses a free online helper to guess titles and authors.</p>
        <div className="button-row">
          <BigButton variant="primary" onClick={() => setStep("choice")}>
            Yes, help me
          </BigButton>
          <BigButton
            variant="plain"
            disabled={saving}
            onClick={() => {
              setSaving(true);
              void skipToNullProvider(onDone);
            }}
          >
            Skip, I'll do it myself
          </BigButton>
        </div>
      </main>
    );
  }

  if (step === "choice") {
    return (
      <main aria-labelledby="ai-choice-heading">
        <h1 id="ai-choice-heading">Pick a helper</h1>
        <div className="stack-sm">
          <RadioRow
            name="ai-provider"
            value="gemini"
            checked={provider === "gemini"}
            onSelect={() => setProvider("gemini")}
            label={PROVIDER_LABELS.gemini}
          />
          <RadioRow
            name="ai-provider"
            value="openai"
            checked={provider === "openai"}
            onSelect={() => setProvider("openai")}
            label={PROVIDER_LABELS.openai}
          />
        </div>
        <BigButton variant="primary" onClick={() => setStep("key")}>
          Next
        </BigButton>
        <button type="button" className="link-button" onClick={() => setStep("intro")}>
          ← Back
        </button>
      </main>
    );
  }

  return (
    <main aria-labelledby="ai-key-heading">
      <h1 id="ai-key-heading">Paste your code from {PROVIDER_LABELS[provider]} here</h1>
      <div className="field">
        <label htmlFor={codeInputId} className="sr-only">
          Your code
        </label>
        <input
          id={codeInputId}
          type="password"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          autoComplete="off"
        />
      </div>
      <p>
        Don't have one yet?{" "}
        <a href={KEY_CREATION_URLS[provider]} target="_blank" rel="noopener noreferrer">
          Get a code
        </a>
      </p>
      <div className="button-row">
        <BigButton
          variant="plain"
          disabled={saving}
          onClick={() => {
            setSaving(true);
            void skipToNullProvider(onDone);
          }}
        >
          Skip for now
        </BigButton>
        <BigButton
          variant="primary"
          disabled={saving || code.trim() === ""}
          onClick={() => {
            setSaving(true);
            void updateSettings({ ai_provider: provider, ai_api_key: code }).then(onDone);
          }}
        >
          Done
        </BigButton>
      </div>
      <button type="button" className="link-button" onClick={() => setStep("choice")}>
        ← Back
      </button>
    </main>
  );
}
