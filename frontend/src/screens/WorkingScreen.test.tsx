import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { WorkingScreen } from "./WorkingScreen";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "generating",
    title: "Fated",
    progress: { chunks_done: 5, chunks_total: 100 },
    ...overrides,
  };
}

describe("WorkingScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the working book, its position, and the friendly status", () => {
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.getByRole("heading")).toHaveTextContent("Working on: Fated");
    expect(screen.getByText("Book 1 of 1")).toBeInTheDocument();
    expect(screen.getByText(/Making the audiobook now/)).toBeInTheDocument();
    expect(screen.getByText(/okay to leave this open/)).toBeInTheDocument();
  });

  it("Pause and Cancel have permanent captions, not tooltips", () => {
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.getByText("Stop for now, come back anytime.")).toBeVisible();
    expect(screen.getByText("Stop working on this book completely.")).toBeVisible();
  });

  it("Pause calls the pause route and refreshes", async () => {
    const user = userEvent.setup();
    const pauseSpy = vi.spyOn(client, "pauseBook").mockResolvedValue({ ok: true });
    const onChanged = vi.fn();
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={onChanged}
        onQuit={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Pause" }));

    expect(pauseSpy).toHaveBeenCalledWith("b1");
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("Cancel requires confirmation before anything happens", async () => {
    const user = userEvent.setup();
    const cancelSpy = vi.spyOn(client, "cancelBook");
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(cancelSpy).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: 'Stop working on "Fated"?' }),
    ).toBeInTheDocument();
  });

  it("keep-partial is the option that actually calls cancel with keep_partial true", async () => {
    const user = userEvent.setup();
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(
      screen.getByRole("button", { name: "Stop, but keep what's done so far" }),
    );

    expect(cancelSpy).toHaveBeenCalledWith("b1", true);
  });

  it("Never mind closes the confirmation without cancelling", async () => {
    const user = userEvent.setup();
    const cancelSpy = vi.spyOn(client, "cancelBook");
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Never mind" }));

    expect(cancelSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Quit for now fires its callback", async () => {
    const user = userEvent.setup();
    const onQuit = vi.fn();
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={onQuit}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Quit for now" }));

    expect(onQuit).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
