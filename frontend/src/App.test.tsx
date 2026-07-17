import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "./api/client";
import App from "./App";
import type { Book, Settings, StatusResponse } from "./api/types";

function settings(overrides: Partial<Settings> = {}): Settings {
  return {
    schema_version: 1,
    books_folder: "C:\\Books",
    output_folder: "C:\\Audiobooks",
    fix_names: true,
    clean_language: true,
    ai_provider: "none",
    has_ai_api_key: false,
    last_voice: "af_heart",
    profanity_words: [],
    ...overrides,
  };
}

function status(overrides: Partial<StatusResponse> = {}): StatusResponse {
  return {
    state: "idle",
    active_book_id: null,
    message: "Add some books to get started.",
    needs_input: null,
    books: [],
    error: null,
    ...overrides,
  };
}

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "pending",
    ...overrides,
  };
}

function mockCore(settingsValue: Settings, statusValue: StatusResponse) {
  vi.spyOn(client, "getSettings").mockResolvedValue(settingsValue);
  vi.spyOn(client, "getWelcomeBack").mockResolvedValue({ pending_book_ids: [] });
  const getStatusSpy = vi.spyOn(client, "getStatus").mockResolvedValue(statusValue);
  vi.spyOn(client, "getDiskSpace").mockResolvedValue({
    estimated_total_bytes: 0,
    any_insufficient: false,
    checked_paths: [],
  });
  return { getStatusSpy };
}

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows first-launch folder setup when no folders are chosen yet", async () => {
    mockCore(settings({ books_folder: "", output_folder: "" }), status());

    render(<App />);

    expect(await screen.findByText("Where are your book files?")).toBeInTheDocument();
  });

  it("goes from folders to AI Helper Setup when no key is present", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getSettings")
      .mockResolvedValueOnce(settings({ books_folder: "", output_folder: "" }))
      .mockResolvedValue(settings({ has_ai_api_key: false }));
    vi.spyOn(client, "getWelcomeBack").mockResolvedValue({ pending_book_ids: [] });
    vi.spyOn(client, "getStatus").mockResolvedValue(status());
    vi.spyOn(client, "pickFolder")
      .mockResolvedValueOnce({ path: "C:\\Books" })
      .mockResolvedValueOnce({ path: "C:\\Audiobooks" });
    vi.spyOn(client, "updateSettings").mockResolvedValue({ ok: true });

    render(<App />);
    await screen.findByText("Where are your book files?");
    await user.click(
      screen.getByRole("button", { name: "Choose folder for your book files" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Choose folder for your finished books" }),
    );
    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(
      await screen.findByText("Want help fixing messy file names automatically?"),
    ).toBeInTheDocument();
  });

  it("skips AI Helper Setup on first launch when a key is already present", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getSettings")
      .mockResolvedValueOnce(settings({ books_folder: "", output_folder: "" }))
      .mockResolvedValue(settings({ has_ai_api_key: true }));
    vi.spyOn(client, "getWelcomeBack").mockResolvedValue({ pending_book_ids: [] });
    vi.spyOn(client, "getStatus").mockResolvedValue(status());
    vi.spyOn(client, "pickFolder")
      .mockResolvedValueOnce({ path: "C:\\Books" })
      .mockResolvedValueOnce({ path: "C:\\Audiobooks" });
    vi.spyOn(client, "updateSettings").mockResolvedValue({ ok: true });
    vi.spyOn(client, "getDiskSpace").mockResolvedValue({
      estimated_total_bytes: 0,
      any_insufficient: false,
      checked_paths: [],
    });

    render(<App />);
    await screen.findByText("Where are your book files?");
    await user.click(
      screen.getByRole("button", { name: "Choose folder for your book files" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Choose folder for your finished books" }),
    );
    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(await screen.findByText("Add your books")).toBeInTheDocument();
  });

  it("shows Welcome back when something is pending, and Continue proceeds to the main flow", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getSettings").mockResolvedValue(settings());
    vi.spyOn(client, "getWelcomeBack").mockResolvedValue({
      pending_book_ids: ["b1"],
    });
    vi.spyOn(client, "getStatus").mockResolvedValue(
      status({
        state: "voice_pick",
        books: [book({ status: "voice_pick", title: "Cursed", voice: "af_heart" })],
      }),
    );
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: [] });

    render(<App />);

    expect(await screen.findByText("📚 Welcome back!")).toBeInTheDocument();
    expect(screen.getByText(/Cursed/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText(/Pick a voice for/)).toBeInTheDocument();
  });

  it("renders Screen 1 for an idle batch with no pending welcome-back", async () => {
    mockCore(settings(), status());

    render(<App />);

    expect(await screen.findByText("Add your books")).toBeInTheDocument();
  });

  it("stays on Screen 1 while every added book is still pending (Start not pressed)", async () => {
    mockCore(
      settings(),
      status({ state: "identifying", books: [book({ status: "pending" })] }),
    );

    render(<App />);

    expect(await screen.findByText("Add your books")).toBeInTheDocument();
    expect(screen.getByText("Fated.epub")).toBeInTheDocument();
  });

  it("routes to Confirm metadata when a book needs identification input", async () => {
    mockCore(
      settings(),
      status({
        state: "identifying",
        active_book_id: "b1",
        needs_input: { book_id: "b1", type: "confirm_metadata" },
        books: [book({ status: "needs_input", title: "Fated" })],
      }),
    );

    render(<App />);

    expect(await screen.findByText(/Let's check Fated's info/)).toBeInTheDocument();
  });

  it("routes to the single-book voice picker at voice_pick", async () => {
    mockCore(
      settings(),
      status({
        state: "voice_pick",
        books: [book({ status: "voice_pick", title: "Fated", voice: "af_heart" })],
      }),
    );
    vi.spyOn(client, "getVoices").mockResolvedValue({
      voices: [{ key: "af_heart", name: "Heart", gender: "Female" }],
    });

    render(<App />);

    expect(await screen.findByText(/Pick a voice for "Fated"/)).toBeInTheDocument();
  });

  it("routes to the Working screen while generating", async () => {
    mockCore(
      settings(),
      status({
        state: "working",
        active_book_id: "b1",
        message: "Making the audiobook now...",
        books: [
          book({
            status: "generating",
            title: "Fated",
            progress: { chunks_done: 1, chunks_total: 10 },
          }),
        ],
      }),
    );

    render(<App />);

    expect(await screen.findByText("Working on: Fated")).toBeInTheDocument();
  });

  it("routes to the collision prompt instead of Working when one is pending", async () => {
    mockCore(
      settings(),
      status({
        state: "working",
        active_book_id: "b1",
        needs_input: {
          book_id: "b1",
          type: "output_collision",
          collision: { artifact: "audiobook", path: "C:\\x" },
        },
        books: [book({ status: "needs_input", title: "Fated" })],
      }),
    );

    render(<App />);

    expect(
      await screen.findByText('You already have a audiobook called "Fated"'),
    ).toBeInTheDocument();
  });

  it("routes to the Review screen when generation finishes", async () => {
    mockCore(
      settings(),
      status({
        state: "review",
        active_book_id: "b1",
        needs_input: { book_id: "b1", type: "review_result" },
        books: [book({ status: "needs_input", title: "Fated" })],
      }),
    );

    render(<App />);

    expect(await screen.findByText(/Fated is ready!/)).toBeInTheDocument();
  });

  it("switches from Review to the fix-it flow locally when she says No", async () => {
    const user = userEvent.setup();
    mockCore(
      settings(),
      status({
        state: "review",
        active_book_id: "b1",
        needs_input: { book_id: "b1", type: "review_result" },
        books: [book({ status: "needs_input", title: "Fated" })],
      }),
    );
    vi.spyOn(client, "submitReview").mockResolvedValue({
      ok: true,
      status: "needs_input",
    });

    render(<App />);
    await screen.findByText(/Fated is ready!/);

    await user.click(screen.getByRole("button", { name: "No, let me fix it" }));

    expect(await screen.findByText(/Let's fix Fated's info/)).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(await screen.findByText(/Fated is ready!/)).toBeInTheDocument();
  });

  it("shows a generic waiting message while identification runs with nothing needing her input", async () => {
    mockCore(
      settings(),
      status({
        state: "identifying",
        message: "Finding out about your books...",
        books: [book({ status: "identifying" })],
      }),
    );

    render(<App />);

    expect(
      await screen.findByText("Finding out about your books..."),
    ).toBeInTheDocument();
  });

  it("Quit for now on the Working screen stops polling the main flow", async () => {
    const user = userEvent.setup();
    mockCore(
      settings(),
      status({
        state: "working",
        active_book_id: "b1",
        books: [book({ status: "generating", title: "Fated" })],
      }),
    );
    vi.spyOn(client, "quitApp").mockResolvedValue({ ok: true });

    render(<App />);
    await screen.findByText("Working on: Fated");

    await user.click(screen.getByRole("button", { name: "Quit for now" }));

    expect(
      await screen.findByText("You can close this window now."),
    ).toBeInTheDocument();
  });

  it("opens Words and Voice History from the More options hub", async () => {
    const user = userEvent.setup();
    mockCore(settings(), status());
    vi.spyOn(client, "getVoiceHistory").mockResolvedValue({ ok: true, history: [] });
    vi.spyOn(client, "getVoices").mockResolvedValue({ voices: [] });

    render(<App />);
    await screen.findByText("Add your books");

    await user.click(screen.getByRole("button", { name: "⚙️ More options" }));
    await screen.findByText("More options");

    await user.click(screen.getByRole("button", { name: "🧼 Words to clean up" }));
    expect(await screen.findByText("Words to clean up")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    await screen.findByText("Add your books");

    await user.click(screen.getByRole("button", { name: "⚙️ More options" }));
    await screen.findByText("More options");
    await user.click(
      screen.getByRole("button", { name: "🎙️ What voice did I use before?" }),
    );
    expect(
      await screen.findByText("🎙️ What voice did I use before?"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Add your books")).toBeInTheDocument();
  });

  it("routes to the generic error screen when a book has errored", async () => {
    mockCore(
      settings(),
      status({
        state: "error",
        error: {
          book_id: "b1",
          summary: "Something went wrong.",
          support_bundle_available: true,
        },
        books: [book({ status: "error" })],
      }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
  });

  it("error screen offers to remove the offending book, so she isn't stuck", async () => {
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    const { getStatusSpy } = mockCore(
      settings(),
      status({
        state: "error",
        error: {
          book_id: "b1",
          summary: "Something went wrong.",
          support_bundle_available: true,
        },
        books: [book({ status: "error" })],
      }),
    );
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Something went wrong" });

    await user.click(
      screen.getByRole("button", { name: 'Remove "Fated.epub" from this batch' }),
    );

    expect(cancelSpy).toHaveBeenCalledWith("b1");
    await vi.waitFor(() => expect(getStatusSpy).toHaveBeenCalledTimes(2));
  });

  it("opens and returns from the folders settings sub-view via the More options hub", async () => {
    const user = userEvent.setup();
    mockCore(settings(), status());
    vi.spyOn(client, "updateSettings").mockResolvedValue({ ok: true });

    render(<App />);
    await screen.findByText("Add your books");

    await user.click(screen.getByRole("button", { name: "⚙️ More options" }));
    await screen.findByText("More options");
    await user.click(screen.getByRole("button", { name: "⚙️ Change my folders" }));
    expect(await screen.findByText("Your folders")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Add your books")).toBeInTheDocument();
  });

  it("shows the app header everywhere, but Home only in a settings sub-view", async () => {
    const user = userEvent.setup();
    mockCore(settings(), status());

    render(<App />);
    await screen.findByText("Add your books");

    expect(screen.getByRole("banner")).toHaveTextContent("Audiobook Maker");
    expect(screen.queryByRole("button", { name: /Home/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "⚙️ More options" }));
    await screen.findByText("More options");

    expect(screen.getByRole("button", { name: "🏠 Home" })).toBeInTheDocument();
  });

  it("Home in a settings sub-view returns to the main flow", async () => {
    const user = userEvent.setup();
    mockCore(settings(), status());

    render(<App />);
    await screen.findByText("Add your books");
    await user.click(screen.getByRole("button", { name: "⚙️ More options" }));
    await screen.findByText("More options");

    await user.click(screen.getByRole("button", { name: "🏠 Home" }));

    expect(await screen.findByText("Add your books")).toBeInTheDocument();
  });

  it("does not show Home mid-batch (working)", async () => {
    mockCore(
      settings(),
      status({
        state: "working",
        active_book_id: "b1",
        books: [book({ status: "generating", title: "Fated" })],
      }),
    );

    render(<App />);
    await screen.findByText("Working on: Fated");

    expect(screen.queryByRole("button", { name: /Home/ })).not.toBeInTheDocument();
  });
});
