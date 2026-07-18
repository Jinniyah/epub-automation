import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { MoreOptionsScreen } from "./MoreOptionsScreen";

function noopHandlers() {
  return {
    onOpenFolders: vi.fn(),
    onOpenWords: vi.fn(),
    onOpenAiHelper: vi.fn(),
    onOpenVoiceHistory: vi.fn(),
    onDone: vi.fn(),
  };
}

describe("MoreOptionsScreen", () => {
  it("each option button fires its own callback", async () => {
    const user = userEvent.setup();
    const handlers = noopHandlers();
    render(<MoreOptionsScreen {...handlers} />);

    await user.click(screen.getByRole("button", { name: "⚙️ Change my folders" }));
    await user.click(screen.getByRole("button", { name: "🧼 Words to clean up" }));
    await user.click(screen.getByRole("button", { name: "🤖 File name helper" }));
    await user.click(
      screen.getByRole("button", { name: "🎙️ What voice did I use before?" }),
    );

    expect(handlers.onOpenFolders).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenWords).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenAiHelper).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenVoiceHistory).toHaveBeenCalledTimes(1);
  });

  it("Done fires its callback", async () => {
    const user = userEvent.setup();
    const handlers = noopHandlers();
    render(<MoreOptionsScreen {...handlers} />);

    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(handlers.onDone).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(<MoreOptionsScreen {...noopHandlers()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  describe("clean up stuck in-progress state", () => {
    it("does nothing until the confirm dialog is accepted", async () => {
      const user = userEvent.setup();
      const cleanupSpy = vi
        .spyOn(apiClient, "cleanupInProgress")
        .mockResolvedValue({ ok: true });
      const handlers = noopHandlers();
      render(<MoreOptionsScreen {...handlers} />);

      await user.click(
        screen.getByRole("button", { name: "🧹 Nuke everything in progress" }),
      );
      expect(
        screen.getByRole("heading", { name: "Clear out everything in progress?" }),
      ).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Never mind" }));

      expect(cleanupSpy).not.toHaveBeenCalled();
      expect(handlers.onDone).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("heading", { name: "Clear out everything in progress?" }),
      ).not.toBeInTheDocument();
    });

    it("calls the cleanup route then returns to the hub on confirm", async () => {
      const user = userEvent.setup();
      const cleanupSpy = vi
        .spyOn(apiClient, "cleanupInProgress")
        .mockResolvedValue({ ok: true });
      const handlers = noopHandlers();
      render(<MoreOptionsScreen {...handlers} />);

      await user.click(
        screen.getByRole("button", { name: "🧹 Nuke everything in progress" }),
      );
      await user.click(screen.getByRole("button", { name: "Yes, clear it out" }));

      expect(cleanupSpy).toHaveBeenCalledTimes(1);
      expect(handlers.onDone).toHaveBeenCalledTimes(1);
    });
  });
});
