import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  it("renders as a real header landmark with the app name", () => {
    render(<AppHeader />);
    const header = screen.getByRole("banner");
    expect(header).toHaveTextContent("Audiobook Maker");
  });

  it("hides Home when it isn't provided (unsafe screens)", () => {
    render(<AppHeader />);
    expect(screen.queryByRole("button", { name: /Home/ })).not.toBeInTheDocument();
  });

  it("shows and fires Home when provided", async () => {
    const user = userEvent.setup();
    const onHome = vi.fn();
    render(<AppHeader onHome={onHome} />);

    await user.click(screen.getByRole("button", { name: "🏠 Home" }));

    expect(onHome).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(<AppHeader onHome={() => {}} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  describe("Quit for now", () => {
    it("hides Quit when it isn't provided", () => {
      render(<AppHeader />);
      expect(
        screen.queryByRole("button", { name: "Quit for now" }),
      ).not.toBeInTheDocument();
    });

    it("does nothing until the confirm dialog is accepted", async () => {
      const user = userEvent.setup();
      const onQuit = vi.fn();
      render(<AppHeader onQuit={onQuit} />);

      await user.click(screen.getByRole("button", { name: "Quit for now" }));
      expect(
        screen.getByRole("heading", { name: "Stop for now?" }),
      ).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Never mind" }));

      expect(onQuit).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("heading", { name: "Stop for now?" }),
      ).not.toBeInTheDocument();
    });

    it("calls onQuit when the confirm dialog is accepted", async () => {
      const user = userEvent.setup();
      const onQuit = vi.fn();
      render(<AppHeader onQuit={onQuit} />);

      await user.click(screen.getByRole("button", { name: "Quit for now" }));
      await user.click(screen.getByRole("button", { name: "Yes, stop for now" }));

      expect(onQuit).toHaveBeenCalledTimes(1);
    });

    it("shows both Home and Quit together when both are provided", () => {
      render(<AppHeader onHome={() => {}} onQuit={() => {}} />);

      expect(screen.getByRole("button", { name: "🏠 Home" })).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Quit for now" }),
      ).toBeInTheDocument();
    });

    it("has no axe violations with the confirm dialog open", async () => {
      const user = userEvent.setup();
      const { container } = render(<AppHeader onQuit={() => {}} />);

      await user.click(screen.getByRole("button", { name: "Quit for now" }));

      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
