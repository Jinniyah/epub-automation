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
});
