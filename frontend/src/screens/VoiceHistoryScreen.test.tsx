import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { VoiceHistoryScreen } from "./VoiceHistoryScreen";

describe("VoiceHistoryScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves voice keys to plain first names", async () => {
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({
      ok: true,
      history: [{ label: "Alex Verus", voice: "bm_george" }],
    });
    vi.spyOn(client, "getVoices").mockResolvedValue({
      voices: [{ key: "bm_george", name: "George", gender: "Male" }],
    });
    render(<VoiceHistoryScreen onDone={() => {}} />);

    expect(await screen.findByText("George")).toBeInTheDocument();
    expect(screen.getByText(/Alex Verus/)).toBeInTheDocument();
  });

  it("shows the legitimately-empty message, distinct from an error", async () => {
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({ ok: true, history: [] });
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: [] });
    render(<VoiceHistoryScreen onDone={() => {}} />);

    expect(
      await screen.findByText(/haven't made any audiobooks yet/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the error state with a Copy details for support action", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({
      ok: false,
      error: "Something went wrong finding your voice history.",
    });
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: [] });
    const bundleSpy = vi
      .spyOn(client, "requestSupportBundle")
      .mockResolvedValue({ ok: true, path: "C:\\log.txt" });
    render(<VoiceHistoryScreen onDone={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Something went wrong finding your voice history.",
    );
    await user.click(screen.getByRole("button", { name: "Copy details for support" }));
    expect(bundleSpy).toHaveBeenCalled();
  });

  it("Done fires its callback", async () => {
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({ ok: true, history: [] });
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: [] });
    const user = userEvent.setup();
    const onDone = vi.fn();
    render(<VoiceHistoryScreen onDone={onDone} />);
    await screen.findByText(/haven't made any audiobooks/);

    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations in the ready state", async () => {
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({
      ok: true,
      history: [{ label: "Alex Verus", voice: "bm_george" }],
    });
    vi.spyOn(client, "getVoices").mockResolvedValue({
      voices: [{ key: "bm_george", name: "George", gender: "Male" }],
    });
    const { container } = render(<VoiceHistoryScreen onDone={() => {}} />);
    await screen.findByText("George");

    expect(await axe(container)).toHaveNoViolations();
  });
});
