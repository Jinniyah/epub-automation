import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { AddBooksScreen } from "./AddBooksScreen";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "pending",
    ...overrides,
  };
}

function noopHandlers() {
  return {
    onChanged: vi.fn(),
    onStart: vi.fn(),
    onOpenFolders: vi.fn(),
    onOpenWords: vi.fn(),
    onOpenAiHelper: vi.fn(),
    onOpenVoiceHistory: vi.fn(),
  };
}

describe("AddBooksScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("Start is disabled with no books", () => {
    render(
      <AddBooksScreen
        books={[]}
        fixNames
        cleanLanguage
        {...noopHandlers()}
      />,
    );

    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  });

  it("lists added books with a Remove button each", async () => {
    const user = userEvent.setup();
    const removeSpy = vi.spyOn(client, "removeBook").mockResolvedValue({ ok: true });
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });
    const handlers = noopHandlers();
    render(
      <AddBooksScreen
        books={[book(), book({ id: "b2", original_filename: "Cursed.epub" })]}
        fixNames
        cleanLanguage
        {...handlers}
      />,
    );

    expect(screen.getByText("Fated.epub")).toBeInTheDocument();
    expect(screen.getByText("Cursed.epub")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);

    expect(removeSpy).toHaveBeenCalledWith("b1");
    expect(handlers.onChanged).toHaveBeenCalled();
  });

  it("choosing a file via the input adds it and surfaces rejections", async () => {
    vi.spyOn(client, "addBooks").mockResolvedValue({
      results: [
        {
          ok: false,
          original_filename: "notabook.txt",
          book_id: null,
          reason: "not_epub",
          message: "That doesn't look like a book file — only .epub files work here",
        },
      ],
    });
    const handlers = noopHandlers();
    render(<AddBooksScreen books={[]} fixNames cleanLanguage {...handlers} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["not an epub"], "notabook.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(
      await screen.findByText(/That doesn't look like a book file/),
    ).toBeInTheDocument();
    expect(handlers.onChanged).toHaveBeenCalled();
  });

  it("warns when disk space is insufficient", async () => {
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 999_999_999_999,
      any_insufficient: true,
      checked_paths: [],
    });
    render(
      <AddBooksScreen books={[book()]} fixNames cleanLanguage {...noopHandlers()} />,
    );

    expect(await screen.findByText(/might not have enough space/)).toBeInTheDocument();
  });

  it("toggles call updateSettings with the flipped value", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });
    render(
      <AddBooksScreen books={[book()]} fixNames cleanLanguage {...noopHandlers()} />,
    );

    await user.click(screen.getByText("🏷️ Fix messy file names"));

    expect(updateSpy).toHaveBeenCalledWith({ fix_names: false });
  });

  it("Start calls startBatch then onStart", async () => {
    const user = userEvent.setup();
    const startSpy = vi.spyOn(client, "startBatch").mockResolvedValue({ ok: true });
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });
    const handlers = noopHandlers();
    render(
      <AddBooksScreen books={[book()]} fixNames cleanLanguage {...handlers} />,
    );

    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(startSpy).toHaveBeenCalled();
    await vi.waitFor(() => expect(handlers.onStart).toHaveBeenCalledTimes(1));
  });

  it("entry point buttons fire their callbacks", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });
    const handlers = noopHandlers();
    render(<AddBooksScreen books={[]} fixNames cleanLanguage {...handlers} />);

    await user.click(screen.getByRole("button", { name: "⚙️ Change my folders" }));
    await user.click(screen.getByRole("button", { name: "🧼 Words to clean up" }));
    await user.click(screen.getByRole("button", { name: "🤖 File name helper" }));
    await user.click(
      screen.getByRole("button", { name: "🎙️ What voice did I use before?" }),
    );

    expect(handlers.onOpenFolders).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenWords).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenAiHelper).toHaveBeenCalledTimes(1);
    expect(handlers.onOpenVoiceHistory).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });
    const { container } = render(
      <AddBooksScreen books={[book()]} fixNames cleanLanguage {...noopHandlers()} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
