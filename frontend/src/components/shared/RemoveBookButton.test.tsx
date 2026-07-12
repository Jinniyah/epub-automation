import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import { RemoveBookButton } from "./RemoveBookButton";

describe("RemoveBookButton", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("has a real accessible name naming the book, not a bare glyph", () => {
    render(
      <RemoveBookButton bookId="b1" bookLabel="Fated" onRemoved={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: 'Remove "Fated" from this batch' }),
    ).toBeInTheDocument();
  });

  it("cancels the book and reports back on click", async () => {
    const user = userEvent.setup();
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    const onRemoved = vi.fn();
    render(
      <RemoveBookButton bookId="b1" bookLabel="Fated" onRemoved={onRemoved} />,
    );

    await user.click(screen.getByRole("button", { name: /Fated/ }));

    expect(cancelSpy).toHaveBeenCalledWith("b1");
    expect(onRemoved).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <RemoveBookButton bookId="b1" bookLabel="Fated" onRemoved={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
