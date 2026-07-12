import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import { LiveRegion } from "./LiveRegion";

describe("LiveRegion", () => {
  it("renders polite messages in a status role, visible not hidden", () => {
    render(<LiveRegion politeness="polite">Making the audiobook now...</LiveRegion>);

    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Making the audiobook now...");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toBeVisible();
  });

  it("renders errors in an assertive alert role", () => {
    render(<LiveRegion politeness="assertive">Something went wrong.</LiveRegion>);

    const region = screen.getByRole("alert");
    expect(region).toHaveAttribute("aria-live", "assertive");
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <LiveRegion politeness="polite">All done!</LiveRegion>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
