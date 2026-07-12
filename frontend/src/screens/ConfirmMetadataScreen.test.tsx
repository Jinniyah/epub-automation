import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ConfirmMetadataScreen } from "./ConfirmMetadataScreen";
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

describe("ConfirmMetadataScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the found metadata combining author as Last, First", () => {
    render(<ConfirmMetadataScreen book={book()} onConfirmed={() => {}} />);

    expect(screen.getByText("Jacka, Benedict")).toBeInTheDocument();
    expect(screen.getByText("Fated")).toBeInTheDocument();
    expect(screen.getByText("Alex Verus")).toBeInTheDocument();
  });

  it("Looks good with no edits confirms with null corrections", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi
      .spyOn(client, "confirmMetadata")
      .mockResolvedValue({ ok: true, status: "voice_pick" });
    const onConfirmed = vi.fn();
    render(<ConfirmMetadataScreen book={book()} onConfirmed={onConfirmed} />);

    await user.click(screen.getByRole("button", { name: "Looks good" }));

    expect(confirmSpy).toHaveBeenCalledWith("b1", null);
    expect(onConfirmed).toHaveBeenCalledTimes(1);
  });

  it("editing the title sends only the changed field", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi
      .spyOn(client, "confirmMetadata")
      .mockResolvedValue({ ok: true, status: "voice_pick" });
    render(<ConfirmMetadataScreen book={book()} onConfirmed={() => {}} />);

    await user.click(screen.getByRole("button", { name: /Title/ }));
    await user.keyboard("Cursed");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Looks good" }));

    expect(confirmSpy).toHaveBeenCalledWith("b1", { title: "Cursed" });
  });

  it("editing the author splits the combined field back into first/last", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi
      .spyOn(client, "confirmMetadata")
      .mockResolvedValue({ ok: true, status: "voice_pick" });
    render(<ConfirmMetadataScreen book={book()} onConfirmed={() => {}} />);

    await user.click(screen.getByRole("button", { name: /Author/ }));
    await user.keyboard("Sanderson, Brandon");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await user.click(screen.getByRole("button", { name: "Looks good" }));

    expect(confirmSpy).toHaveBeenCalledWith("b1", {
      author_first: "Brandon",
      author_last: "Sanderson",
    });
  });

  it("shows different heading copy when AI enrichment failed", () => {
    render(
      <ConfirmMetadataScreen
        book={book({ title: "", author_first: "", author_last: "" })}
        enrichmentFailed
        onConfirmed={() => {}}
      />,
    );

    expect(screen.getByRole("heading")).toHaveTextContent(/couldn't quite figure out/);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <ConfirmMetadataScreen book={book()} onConfirmed={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("asOverlay mode patches metadata via updateBookMetadata, not confirmMetadata", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateBookMetadata")
      .mockResolvedValue({ ok: true, status: "voice_pick" });
    const confirmSpy = vi.spyOn(client, "confirmMetadata");
    const onConfirmed = vi.fn();
    render(
      <ConfirmMetadataScreen
        book={book()}
        asOverlay
        onConfirmed={onConfirmed}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateSpy).toHaveBeenCalledWith("b1", {});
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(onConfirmed).toHaveBeenCalledTimes(1);
  });

  it("asOverlay mode does not render a duplicate heading", () => {
    render(<ConfirmMetadataScreen book={book()} asOverlay onConfirmed={() => {}} />);
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});
