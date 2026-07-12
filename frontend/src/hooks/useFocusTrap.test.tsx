import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useFocusTrap } from "./useFocusTrap";

function TestOverlay({ active, onClose }: { active: boolean; onClose: () => void }) {
  const ref = useFocusTrap<HTMLDivElement>({ active, onClose });
  if (!active) return null;
  return (
    <div ref={ref} data-testid="overlay">
      <button type="button">First</button>
      <button type="button">Last</button>
    </div>
  );
}

function Harness({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <TestOverlay
        active={open}
        onClose={() => {
          setOpen(false);
          onClose();
        }}
      />
    </div>
  );
}

describe("useFocusTrap", () => {
  it("moves focus to the first focusable element on open", async () => {
    const user = userEvent.setup();
    render(<Harness onClose={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
  });

  it("wraps Tab from the last element back to the first", async () => {
    const user = userEvent.setup();
    render(<Harness onClose={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    screen.getByRole("button", { name: "Last" }).focus();
    await user.tab();

    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
  });

  it("wraps Shift+Tab from the first element back to the last", async () => {
    const user = userEvent.setup();
    render(<Harness onClose={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
    await user.tab({ shift: true });

    expect(screen.getByRole("button", { name: "Last" })).toHaveFocus();
  });

  it("calls onClose when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "Open" }));

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("returns focus to the trigger element after closing", async () => {
    const user = userEvent.setup();
    render(<Harness onClose={() => {}} />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);

    await user.keyboard("{Escape}");

    expect(opener).toHaveFocus();
  });
});
