import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { CollisionPrompt } from "./CollisionPrompt";

describe("CollisionPrompt", () => {
  it("names the audiobook artifact distinctly from an epub", () => {
    render(
      <CollisionPrompt bookTitle="Fated" artifact="audiobook" onChoice={() => {}} />,
    );
    expect(screen.getByRole("heading")).toHaveTextContent(
      'You already have a audiobook called "Fated"',
    );
  });

  it("Keep both and Replace report their choice", async () => {
    const user = userEvent.setup();
    const onChoice = vi.fn();
    render(<CollisionPrompt bookTitle="Fated" artifact="epub" onChoice={onChoice} />);

    await user.click(screen.getByRole("button", { name: "Keep both" }));
    expect(onChoice).toHaveBeenCalledWith("keep_both");

    await user.click(screen.getByRole("button", { name: "Replace it" }));
    expect(onChoice).toHaveBeenCalledWith("replace");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <CollisionPrompt bookTitle="Fated" artifact="epub" onChoice={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
