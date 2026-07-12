import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import { VoicePicker } from "./VoicePicker";
import type { VoiceChoice } from "../../api/types";

const VOICES: VoiceChoice[] = [
  { key: "af_heart", name: "Heart", gender: "Female" },
  { key: "bm_george", name: "George", gender: "Male" },
];

describe("VoicePicker", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a loading message before voices arrive, then the list", async () => {
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: VOICES });
    render(
      <VoicePicker bookLabel='"Fated"' initialVoice="af_heart" onNext={() => {}} />,
    );

    expect(screen.getByText(/Getting voice samples ready/)).toBeInTheDocument();

    expect(await screen.findByText("Heart")).toBeInTheDocument();
    expect(screen.getByText("George")).toBeInTheDocument();
  });

  it("uses a preloaded voices list without fetching its own", () => {
    const getVoicesSpy = vi.spyOn(client, "getVoices");
    render(
      <VoicePicker
        bookLabel='"Fated"'
        initialVoice="af_heart"
        voices={VOICES}
        onNext={() => {}}
      />,
    );

    expect(screen.getByText("Heart")).toBeInTheDocument();
    expect(getVoicesSpy).not.toHaveBeenCalled();
  });

  it("marks the last-used voice with a badge", () => {
    render(
      <VoicePicker
        bookLabel='"Fated"'
        initialVoice="af_heart"
        lastUsedVoice="bm_george"
        voices={VOICES}
        onNext={() => {}}
      />,
    );

    expect(screen.getByText(/last used/)).toBeInTheDocument();
  });

  it("Listen plays the sample without selecting the row", async () => {
    const user = userEvent.setup();
    render(
      <VoicePicker
        bookLabel='"Fated"'
        initialVoice="af_heart"
        voices={VOICES}
        onNext={() => {}}
      />,
    );
    const playSpy = vi
      .spyOn(window.HTMLMediaElement.prototype, "play")
      .mockResolvedValue();

    await user.click(screen.getByRole("button", { name: "Play preview: George" }));

    expect(playSpy).toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: /Heart/ })).toBeChecked();
  });

  it("Next reports the currently selected voice", async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    render(
      <VoicePicker
        bookLabel='"Fated"'
        initialVoice="af_heart"
        voices={VOICES}
        onNext={onNext}
      />,
    );

    await user.click(screen.getByText("George"));
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(onNext).toHaveBeenCalledWith("bm_george");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <VoicePicker
        bookLabel='"Fated"'
        initialVoice="af_heart"
        voices={VOICES}
        onNext={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
