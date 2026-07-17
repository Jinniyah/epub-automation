import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
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
});
