import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { StepProgress } from "./StepProgress";

describe("StepProgress", () => {
  it("marks the current step with aria-current=step", () => {
    render(<StepProgress current="choose_voice" />);

    const current = screen.getByText("Choose Voice").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Add Books").closest("li")).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("shows a checkmark glyph for completed steps, not just a color change", () => {
    render(<StepProgress current="convert" />);

    // "Add Books" and "Confirm Info" precede "Convert" -> completed.
    const addBooksItem = screen.getByText("Add Books").closest("li");
    expect(addBooksItem).toHaveTextContent("✓");
    // "Review" comes after "Convert" -> still upcoming, no checkmark.
    const reviewItem = screen.getByText("Review").closest("li");
    expect(reviewItem).not.toHaveTextContent("✓");
  });

  it("renders the active book title on its own line, tied to the nav via aria-describedby", () => {
    render(<StepProgress current="review" activeBookTitle="Fated" />);

    const nav = screen.getByRole("navigation", { name: "Progress" });
    const bookLine = screen.getByText(/Fated/);
    expect(nav).toHaveAttribute("aria-describedby", bookLine.id);
  });

  it("omits the book line entirely when there is no active book", () => {
    render(<StepProgress current="add_books" />);

    const nav = screen.getByRole("navigation", { name: "Progress" });
    expect(nav).not.toHaveAttribute("aria-describedby");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <StepProgress current="confirm_info" activeBookTitle="Fated" />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders a completed step named in clickableSteps as a real button", async () => {
    const onStepClick = vi.fn();
    const user = userEvent.setup();
    render(
      <StepProgress
        current="choose_voice"
        clickableSteps={["confirm_info"]}
        onStepClick={onStepClick}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Confirm Info/ }));
    expect(onStepClick).toHaveBeenCalledWith("confirm_info");
  });

  it("leaves a completed step not named in clickableSteps as plain text", () => {
    render(
      <StepProgress
        current="choose_voice"
        clickableSteps={["confirm_info"]}
        onStepClick={vi.fn()}
      />,
    );

    // "Add Books" is also complete at this point, but wasn't opted in.
    expect(screen.queryByRole("button", { name: /Add Books/ })).not.toBeInTheDocument();
  });

  it("never makes the current or upcoming steps clickable, even if listed", () => {
    render(
      <StepProgress
        current="choose_voice"
        clickableSteps={["choose_voice", "convert"]}
        onStepClick={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /Choose Voice/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Convert/ })).not.toBeInTheDocument();
  });

  it("stays plain text with no onStepClick handler, even if clickableSteps is set", () => {
    render(<StepProgress current="choose_voice" clickableSteps={["confirm_info"]} />);

    expect(screen.queryByRole("button", { name: /Confirm Info/ })).not.toBeInTheDocument();
  });
});
