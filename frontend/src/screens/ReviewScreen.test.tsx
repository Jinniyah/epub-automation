import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ReviewScreen } from "./ReviewScreen";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "needs_input",
    title: "Fated",
    author_first: "Benedict",
    author_last: "Jacka",
    series: "Alex Verus",
    series_number: "1",
    ...overrides,
  };
}

describe("ReviewScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the finished book's details", () => {
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />);

    expect(screen.getByRole("heading")).toHaveTextContent("Fated is ready!");
    expect(screen.getByText("Jacka, Benedict")).toBeInTheDocument();
    expect(screen.getByText("Alex Verus #1")).toBeInTheDocument();
  });

  it("Yes, looks good submits looks_good:true and calls onDone", async () => {
    const user = userEvent.setup();
    const reviewSpy = vi
      .spyOn(client, "submitReview")
      .mockResolvedValue({ ok: true, status: "complete" });
    const onDone = vi.fn();
    render(<ReviewScreen book={book()} onDone={onDone} onFixIt={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Yes, looks good" }));

    expect(reviewSpy).toHaveBeenCalledWith("b1", true);
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
  });

  it("No, let me fix it submits looks_good:false and calls onFixIt", async () => {
    const user = userEvent.setup();
    const reviewSpy = vi
      .spyOn(client, "submitReview")
      .mockResolvedValue({ ok: true, status: "needs_input" });
    const onFixIt = vi.fn();
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={onFixIt} />);

    await user.click(screen.getByRole("button", { name: "No, let me fix it" }));

    expect(reviewSpy).toHaveBeenCalledWith("b1", false);
    await vi.waitFor(() => expect(onFixIt).toHaveBeenCalledTimes(1));
  });

  it("the step-progress bar's Confirm Info step does the same thing as No, let me fix it", async () => {
    const user = userEvent.setup();
    const reviewSpy = vi
      .spyOn(client, "submitReview")
      .mockResolvedValue({ ok: true, status: "needs_input" });
    const onFixIt = vi.fn();
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={onFixIt} />);

    await user.click(screen.getByRole("button", { name: /Confirm Info/ }));

    expect(reviewSpy).toHaveBeenCalledWith("b1", false);
    await vi.waitFor(() => expect(onFixIt).toHaveBeenCalledTimes(1));
  });

  it("See the audiobook files opens this book's own folder", async () => {
    const user = userEvent.setup();
    const openSpy = vi.spyOn(client, "openBookFolder").mockResolvedValue({ ok: true });
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />);

    await user.click(screen.getByRole("button", { name: "📂 See the audiobook files" }));

    expect(openSpy).toHaveBeenCalledWith("b1");
  });

  it("shows a friendly message if the folder can't be opened", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "openBookFolder").mockResolvedValue({ ok: false });
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />);

    await user.click(screen.getByRole("button", { name: "📂 See the audiobook files" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't open that folder.",
    );
  });

  it("See all my finished books opens the general output folder", async () => {
    const user = userEvent.setup();
    const openSpy = vi
      .spyOn(client, "openOutputFolder")
      .mockResolvedValue({ ok: true });
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />);

    await user.click(screen.getByRole("button", { name: "📂 See all my finished books" }));

    expect(openSpy).toHaveBeenCalled();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks 'Review' as the current step, with this book active", () => {
    render(<ReviewScreen book={book()} onDone={() => {}} onFixIt={() => {}} />);

    expect(screen.getByText("Review").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.getByText(/📖 Fated/)).toBeInTheDocument();
  });
});
