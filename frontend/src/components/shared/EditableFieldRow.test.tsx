import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { EditableFieldRow } from "./EditableFieldRow";

describe("EditableFieldRow", () => {
  it("shows the label and value", () => {
    render(<EditableFieldRow label="Title" value="Fated" onEdit={() => {}} />);
    expect(screen.getByText("Fated")).toBeInTheDocument();
  });

  it("shows a placeholder when the value is empty, not a blank row", () => {
    render(<EditableFieldRow label="Series" value="" onEdit={() => {}} />);
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });

  it("is a real button that calls onEdit", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(<EditableFieldRow label="Title" value="Fated" onEdit={onEdit} />);

    await user.click(screen.getByRole("button"));

    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <EditableFieldRow label="Title" value="Fated" onEdit={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
