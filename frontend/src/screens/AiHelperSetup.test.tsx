import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { AiHelperSetup } from "./AiHelperSetup";

describe("AiHelperSetup", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("top-level Skip routes straight to NullProvider and finishes", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    const onDone = vi.fn();
    render(<AiHelperSetup onDone={onDone} />);

    await user.click(screen.getByRole("button", { name: "Skip, I'll do it myself" }));

    expect(updateSpy).toHaveBeenCalledWith({ ai_provider: "none" });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it("Yes -> provider choice -> key entry, never showing raw provider names", async () => {
    const user = userEvent.setup();
    render(<AiHelperSetup onDone={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Yes, help me" }));

    expect(screen.getByText("Google (free)")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.queryByText(/Gemini/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(
      screen.getByRole("heading", { name: /Paste your code from Google \(free\) here/ }),
    ).toBeInTheDocument();
  });

  it("key entry Skip for now also routes to NullProvider", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    const onDone = vi.fn();
    render(<AiHelperSetup onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Yes, help me" }));
    await user.click(screen.getByRole("button", { name: "Next" }));

    await user.click(screen.getByRole("button", { name: "Skip for now" }));

    expect(updateSpy).toHaveBeenCalledWith({ ai_provider: "none" });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it("Done is disabled until a code is entered, then saves the provider + key", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    const onDone = vi.fn();
    render(<AiHelperSetup onDone={onDone} />);
    await user.click(screen.getByRole("button", { name: "Yes, help me" }));
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();

    await user.type(screen.getByLabelText("Your code"), "secret-code");
    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(updateSpy).toHaveBeenCalledWith({
      ai_provider: "gemini",
      ai_api_key: "secret-code",
    });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it("the code field masks input like a password field", async () => {
    render(<AiHelperSetup onDone={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Yes, help me" }));
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByLabelText("Your code")).toHaveAttribute("type", "password");
  });

  it("has no axe violations on the intro step", async () => {
    const { container } = render(<AiHelperSetup onDone={() => {}} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
