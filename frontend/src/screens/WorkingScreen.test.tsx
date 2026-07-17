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

/** A promise the test controls the resolution of, for asserting on the
 * in-flight (button disabled/relabeled) state before the API call
 * settles. */
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
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

  it("shows the chunk-progress readout and a matching progress bar", () => {
    render(
      <WorkingScreen
        books={[book({ progress: { chunks_done: 5, chunks_total: 100 } })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    // 5 chunks done -- chunk 6 is the one currently in flight.
    expect(screen.getByText("Working on file 6 of 100...")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("value", "5");
    expect(bar).toHaveAttribute("max", "100");
  });

  it("caps the readout at the total once every chunk is done", () => {
    render(
      <WorkingScreen
        books={[book({ progress: { chunks_done: 100, chunks_total: 100 } })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.getByText("Working on file 100 of 100...")).toBeInTheDocument();
  });

  it("shows no chunk-progress readout before any progress is reported", () => {
    render(
      <WorkingScreen
        books={[book({ progress: undefined })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.queryByText(/Working on file/)).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
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

  it("Pause disables itself immediately, before the request settles", async () => {
    const user = userEvent.setup();
    const gate = deferred<{ ok: true }>();
    vi.spyOn(client, "pauseBook").mockReturnValue(gate.promise);
    render(
      <WorkingScreen
        books={[book()]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Pause" }));

    expect(screen.getByRole("button", { name: "Pausing…" })).toBeDisabled();
    gate.resolve({ ok: true });
  });

  it("a paused book shows a Paused badge and a Resume button instead of Pause", () => {
    render(
      <WorkingScreen
        books={[book({ status: "paused" })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "▶ Resume" })).toBeInTheDocument();
  });

  it("a paused book still shows its last-known chunk progress", () => {
    render(
      <WorkingScreen
        books={[
          book({
            status: "paused",
            progress: { chunks_done: 42, chunks_total: 100 },
          }),
        ]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );

    expect(screen.getByText("Working on file 43 of 100...")).toBeInTheDocument();
  });

  it("Resume calls start-generation and refreshes, disabling itself meanwhile", async () => {
    const user = userEvent.setup();
    const gate = deferred<{ ok: true }>();
    const startSpy = vi.spyOn(client, "startGeneration").mockReturnValue(gate.promise);
    const onChanged = vi.fn();
    render(
      <WorkingScreen
        books={[book({ status: "paused" })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={onChanged}
        onQuit={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "▶ Resume" }));

    expect(startSpy).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Resuming…" })).toBeDisabled();
    gate.resolve({ ok: true });
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

  it("answering the cancel dialog closes it immediately and disables Cancel/Pause meanwhile", async () => {
    const user = userEvent.setup();
    const gate = deferred<{ ok: true; status: string }>();
    vi.spyOn(client, "cancelBook").mockReturnValue(gate.promise);
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

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stopping…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Pause" })).toBeDisabled();
    gate.resolve({ ok: true, status: "cancelled" });
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

  it("has no axe violations while paused", async () => {
    const { container } = render(
      <WorkingScreen
        books={[book({ status: "paused" })]}
        activeBookId="b1"
        message="Making the audiobook now..."
        onChanged={() => {}}
        onQuit={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
