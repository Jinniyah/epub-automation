import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { FieldCorrectionPopup } from "./FieldCorrectionPopup";

describe("FieldCorrectionPopup", () => {
  it("pre-fills and pre-selects the existing value so typing replaces it", async () => {
    const user = userEvent.setup();
    render(
      <FieldCorrectionPopup
        fieldLabel="Author"
        initialValue="Jacka, Benedict"
        onSave={() => {}}
        onClose={() => {}}
      />,
    );

    const input = screen.getByLabelText("Author") as HTMLInputElement;
    expect(input).toHaveValue("Jacka, Benedict");
    expect(input).toHaveFocus();

    await user.keyboard("New Author");

    expect(input).toHaveValue("New Author");
  });

  it("Clear empties the field in one tap", async () => {
    const user = userEvent.setup();
    render(
      <FieldCorrectionPopup
        fieldLabel="Title"
        initialValue="Fated"
        onSave={() => {}}
        onClose={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "✕ Clear" }));

    expect(screen.getByLabelText("Title")).toHaveValue("");
  });

  it("Save calls onSave with the current value", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <FieldCorrectionPopup
        fieldLabel="Series"
        initialValue="Alex Verus"
        onSave={onSave}
        onClose={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith("Alex Verus");
  });

  it("Escape closes without saving", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(
      <FieldCorrectionPopup
        fieldLabel="Series"
        initialValue="Alex Verus"
        onSave={onSave}
        onClose={onClose}
      />,
    );

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("traps focus inside the overlay", async () => {
    const user = userEvent.setup();
    render(
      <FieldCorrectionPopup
        fieldLabel="Author"
        initialValue="Jacka, Benedict"
        onSave={() => {}}
        onClose={() => {}}
      />,
    );

    await user.tab(); // input -> Clear
    await user.tab(); // Clear -> Save
    await user.tab(); // Save -> wraps back to input

    expect(screen.getByLabelText("Author")).toHaveFocus();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <FieldCorrectionPopup
        fieldLabel="Author"
        initialValue="Jacka, Benedict"
        onSave={() => {}}
        onClose={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
