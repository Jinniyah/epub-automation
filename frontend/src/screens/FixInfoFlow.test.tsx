import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { FixInfoFlow } from "./FixInfoFlow";
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

describe("FixInfoFlow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("steps through Author, Title, Series, Series Number for a book in a series", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "retagBook").mockResolvedValue({ ok: true, status: "complete" });
    render(<FixInfoFlow book={book()} onDone={() => {}} onCancel={() => {}} />);

    expect(screen.getByText("Author")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Title")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Series")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Series Number")).toBeInTheDocument();
  });

  it("has no Back on the first field, and Back returns to the previous field with its value kept", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "retagBook").mockResolvedValue({ ok: true, status: "complete" });
    render(<FixInfoFlow book={book()} onDone={() => {}} onCancel={() => {}} />);

    expect(screen.queryByRole("button", { name: "← Back" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" })); // Author -> Title
    expect(screen.getByLabelText("Title")).toHaveValue("Fated");
    await user.keyboard("Cursed");

    await user.click(screen.getByRole("button", { name: "← Back" })); // Title -> Author

    expect(screen.getByText("Author")).toBeInTheDocument();
    expect(screen.getByLabelText("Author")).toHaveValue("Jacka, Benedict");
  });

  it("skips the Series steps for a standalone book", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "retagBook").mockResolvedValue({ ok: true, status: "complete" });
    render(
      <FixInfoFlow
        book={book({ series: undefined, series_number: undefined })}
        onDone={() => {}}
        onCancel={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Next" })); // Author -> Title
    await user.click(screen.getByRole("button", { name: "Next" })); // Title -> submits retag

    expect(await screen.findByText("✅ Fixed!")).toBeInTheDocument();
  });

  it("submits the retag with edited values after the last field, then shows Fixed", async () => {
    const user = userEvent.setup();
    const retagSpy = vi
      .spyOn(client, "retagBook")
      .mockResolvedValue({ ok: true, status: "complete" });
    render(
      <FixInfoFlow
        book={book({ series: undefined, series_number: undefined })}
        onDone={() => {}}
        onCancel={() => {}}
      />,
    );

    await user.keyboard("Sanderson, Brandon");
    await user.click(screen.getByRole("button", { name: "Next" })); // Author
    await user.keyboard("Words of Radiance");
    await user.click(screen.getByRole("button", { name: "Next" })); // Title -> submit

    await screen.findByText("✅ Fixed!");
    expect(retagSpy).toHaveBeenCalledWith("b1", {
      title: "Words of Radiance",
      author_first: "Brandon",
      author_last: "Sanderson",
    });
  });

  it("Fixed screen offers to see the audiobook files and a Done button", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "retagBook").mockResolvedValue({ ok: true, status: "complete" });
    const openSpy = vi.spyOn(client, "openBookFolder").mockResolvedValue({ ok: true });
    const onDone = vi.fn();
    render(
      <FixInfoFlow
        book={book({ series: undefined, series_number: undefined })}
        onDone={onDone}
        onCancel={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("✅ Fixed!");

    await user.click(screen.getByRole("button", { name: "📂 See the audiobook files" }));
    expect(openSpy).toHaveBeenCalledWith("b1");

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("Escape on the first field cancels the whole flow", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<FixInfoFlow book={book()} onDone={() => {}} onCancel={onCancel} />);

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <FixInfoFlow book={book()} onDone={() => {}} onCancel={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks 'Review' as the current step throughout, with this book active", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "retagBook").mockResolvedValue({ ok: true, status: "complete" });
    render(
      <FixInfoFlow
        book={book({ series: undefined, series_number: undefined })}
        onDone={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByText("Review").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.getByText(/📖 Fated/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next" })); // Author -> Title
    await user.click(screen.getByRole("button", { name: "Next" })); // Title -> submits (fixing phase)
    await screen.findByText("✅ Fixed!");

    expect(screen.getByText("Review").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.getByText(/📖 Fated/)).toBeInTheDocument();
  });
});
