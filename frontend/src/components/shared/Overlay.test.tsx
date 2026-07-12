import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { Overlay } from "./Overlay";

describe("Overlay", () => {
  it("renders as a labelled, modal dialog", () => {
    render(
      <Overlay titleId="t1" title="Pick a helper" onClose={() => {}}>
        <button type="button">Next</button>
      </Overlay>,
    );

    const dialog = screen.getByRole("dialog", { name: "Pick a helper" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <Overlay titleId="t2" title="Pick a helper" onClose={() => {}}>
        <button type="button">Next</button>
      </Overlay>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
