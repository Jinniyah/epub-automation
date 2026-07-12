import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ErrorScreen } from "./ErrorScreen";

describe("ErrorScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the friendly summary in an assertive live region", () => {
    render(
      <ErrorScreen
        summary="Something went wrong."
        onBackToStart={() => {}}
        onRemoved={() => {}}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });

  it("Copy details for support saves a bundle and shows where", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "requestSupportBundle").mockResolvedValue({
      ok: true,
      path: "C:\\logs\\support_bundle.txt",
    });
    render(
      <ErrorScreen
        summary="Something went wrong."
        onBackToStart={() => {}}
        onRemoved={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Copy details for support" }));

    expect(
      await screen.findByText(/Saved to: C:\\logs\\support_bundle.txt/),
    ).toBeInTheDocument();
  });

  it("always offers a way back", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    render(
      <ErrorScreen
        summary="Something went wrong."
        onBackToStart={onBack}
        onRemoved={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Back to Add Books" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ErrorScreen
        summary="Something went wrong."
        onBackToStart={() => {}}
        onRemoved={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers to remove the offending book when one is identified, and it actually removes it", async () => {
    const user = userEvent.setup();
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    const onRemoved = vi.fn();
    render(
      <ErrorScreen
        summary="Something went wrong."
        bookId="b1"
        bookLabel="Fated"
        onBackToStart={() => {}}
        onRemoved={onRemoved}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: 'Remove "Fated" from this batch' }),
    );

    expect(cancelSpy).toHaveBeenCalledWith("b1");
    expect(onRemoved).toHaveBeenCalledTimes(1);
  });

  it("has no Remove button when no book could be identified", () => {
    render(
      <ErrorScreen
        summary="Something went wrong."
        onBackToStart={() => {}}
        onRemoved={() => {}}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /Remove/ }),
    ).not.toBeInTheDocument();
  });
});
