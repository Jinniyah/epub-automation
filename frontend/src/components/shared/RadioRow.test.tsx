import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { RadioRow } from "./RadioRow";

function Group({ onListen }: { onListen: (v: string) => void }) {
  const [value, setValue] = useState("af_heart");
  return (
    <div>
      <RadioRow
        name="voice"
        value="af_heart"
        checked={value === "af_heart"}
        onSelect={setValue}
        label="Heart"
        action={{ label: "Play preview: Heart", onClick: () => onListen("af_heart") }}
      />
      <RadioRow
        name="voice"
        value="bm_george"
        checked={value === "bm_george"}
        onSelect={setValue}
        label="George"
        badge="last used"
        action={{
          label: "Play preview: George",
          onClick: () => onListen("bm_george"),
        }}
      />
    </div>
  );
}

describe("RadioRow", () => {
  it("selecting via a label click checks the underlying radio", async () => {
    const user = userEvent.setup();
    render(<Group onListen={() => {}} />);

    await user.click(screen.getByText("George"));

    expect(screen.getByRole("radio", { name: /George/ })).toBeChecked();
  });

  it("is selectable via keyboard (native radio-group arrow navigation)", async () => {
    const user = userEvent.setup();
    render(<Group onListen={() => {}} />);

    // Tab enters a native radio group at whichever radio is currently
    // checked (Heart) -- the rest of the group is reached with arrow
    // keys, not Tab, which is standard native radio behavior and what
    // makes this keyboard-operable at all (03-gui-ux-design.md
    // §Operable) without any hand-rolled key handling.
    await user.tab();
    expect(screen.getByRole("radio", { name: /Heart/ })).toHaveFocus();

    await user.keyboard("{ArrowDown}");

    expect(screen.getByRole("radio", { name: /George/ })).toBeChecked();
  });

  it("clicking the nested Listen button does not select the row", async () => {
    const user = userEvent.setup();
    const onListen = vi.fn();
    render(<Group onListen={onListen} />);

    await user.click(screen.getByRole("button", { name: "Play preview: George" }));

    expect(onListen).toHaveBeenCalledWith("bm_george");
    expect(screen.getByRole("radio", { name: /George/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Heart/ })).toBeChecked();
  });

  it("shows the badge as visible text, not color alone", () => {
    render(<Group onListen={() => {}} />);
    expect(screen.getByText(/last used/)).toBeVisible();
  });

  it("has no axe violations", async () => {
    const { container } = render(<Group onListen={() => {}} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
