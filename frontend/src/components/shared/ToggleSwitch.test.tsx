import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { ToggleSwitch } from "./ToggleSwitch";

describe("ToggleSwitch", () => {
  it("shows On/Off as real visible text, not color alone", () => {
    render(
      <ToggleSwitch label="Fix messy file names" checked={true} onChange={() => {}} />,
    );
    expect(screen.getByText("On")).toBeVisible();
  });

  it("clicking anywhere in the row toggles it", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ToggleSwitch label="Clean up bad language" checked={true} onChange={onChange} />,
    );

    await user.click(screen.getByText("Clean up bad language"));

    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("is a real checkbox reachable via keyboard", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ToggleSwitch label="Fix messy file names" checked={false} onChange={onChange} />);

    await user.tab();
    await user.keyboard(" ");

    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ToggleSwitch label="Fix messy file names" checked={true} onChange={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
