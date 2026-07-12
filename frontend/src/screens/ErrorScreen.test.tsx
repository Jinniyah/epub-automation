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
      <ErrorScreen summary="Something went wrong." onBackToStart={() => {}} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });

  it("Copy details for support saves a bundle and shows where", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "requestSupportBundle").mockResolvedValue({
      ok: true,
      path: "C:\\logs\\support_bundle.txt",
    });
    render(<ErrorScreen summary="Something went wrong." onBackToStart={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Copy details for support" }));

    expect(
      await screen.findByText(/Saved to: C:\\logs\\support_bundle.txt/),
    ).toBeInTheDocument();
  });

  it("always offers a way back", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    render(<ErrorScreen summary="Something went wrong." onBackToStart={onBack} />);

    await user.click(screen.getByRole("button", { name: "Back to Add Books" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ErrorScreen summary="Something went wrong." onBackToStart={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
