import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { BigButton } from "./BigButton";

describe("BigButton", () => {
  it("fires onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<BigButton onClick={onClick}>Start</BigButton>);

    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("wires a permanent caption into the button's accessible description, not a tooltip", () => {
    render(
      <BigButton caption="Stop for now, come back anytime.">Pause</BigButton>,
    );

    const button = screen.getByRole("button", { name: "Pause" });
    expect(screen.getByText("Stop for now, come back anytime.")).toBeVisible();
    expect(button).toHaveAccessibleDescription("Stop for now, come back anytime.");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <BigButton variant="danger" caption="Stop working on this book completely.">
        Cancel
      </BigButton>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
