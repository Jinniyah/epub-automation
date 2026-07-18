import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { VoiceAssignmentScreen } from "./VoiceAssignmentScreen";
import type { Book, VoiceChoice } from "../api/types";

const VOICES: VoiceChoice[] = [
  { key: "af_heart", name: "Heart", gender: "Female" },
  { key: "bm_george", name: "George", gender: "Male" },
];

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "voice_pick",
    title: "Fated",
    series: "Alex Verus",
    series_number: "1",
    voice: "af_heart",
    ...overrides,
  };
}

function setUpVoices() {
  vi.spyOn(client, "getVoices").mockResolvedValue({ voices: VOICES });
}

describe("VoiceAssignmentScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("single-book mode offers a way to re-edit metadata before picking a voice", async () => {
    setUpVoices();
    const updateSpy = vi
      .spyOn(client, "updateBookMetadata")
      .mockResolvedValue({ ok: true, status: "voice_pick" });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen books={[book()]} lastVoice="af_heart" onChanged={onChanged} />,
    );
    await screen.findByText("Heart");

    await user.click(
      screen.getByRole("button", { name: "✏️ Not quite right? Fix Fated's info" }),
    );

    expect(
      screen.getByRole("dialog", { name: 'Update "Fated"\'s info' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(updateSpy).toHaveBeenCalledWith("b1", {});
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("renders the single full picker for one book, and assigning advances", async () => {
    setUpVoices();
    const assignSpy = vi
      .spyOn(client, "assignVoice")
      .mockResolvedValue({ ok: true, voice: "bm_george" });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen books={[book()]} lastVoice="af_heart" onChanged={onChanged} />,
    );

    expect(await screen.findByText("Heart")).toBeInTheDocument();
    await user.click(screen.getByText("George"));
    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(assignSpy).toHaveBeenCalledWith("b1", "bm_george");
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("single-book mode offers to remove the book, in case it was added by accident", async () => {
    setUpVoices();
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen books={[book()]} lastVoice="af_heart" onChanged={onChanged} />,
    );
    await screen.findByText("Heart");

    await user.click(
      screen.getByRole("button", { name: 'Remove "Fated" from this batch' }),
    );

    expect(cancelSpy).toHaveBeenCalledWith("b1");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("table mode offers a per-row Remove alongside Change Voice", async () => {
    setUpVoices();
    const cancelSpy = vi
      .spyOn(client, "cancelBook")
      .mockResolvedValue({ ok: true, status: "cancelled" });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1" }), book({ id: "b2", title: "Cursed", series: undefined })]}
        onChanged={onChanged}
      />,
    );
    await screen.findAllByText("Heart");

    await user.click(
      screen.getByRole("button", { name: 'Remove "Fated" from this batch' }),
    );

    expect(cancelSpy).toHaveBeenCalledWith("b1");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("renders a real <table> for more than one book", async () => {
    setUpVoices();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1" }), book({ id: "b2", title: "Cursed", series: undefined })]}
        onChanged={() => {}}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Book" })).toBeInTheDocument();
    expect(await screen.findAllByText("Heart")).toHaveLength(2);
  });

  it("Change Voice opens an overlay scoped to that row only", async () => {
    setUpVoices();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1", title: "Fated" }), book({ id: "b2", title: "Cursed" })]}
        onChanged={() => {}}
      />,
    );
    await screen.findAllByText("Heart");

    await user.click(screen.getAllByRole("button", { name: "Change Voice" })[0]);

    expect(
      screen.getByRole("dialog", { name: 'Change voice for "Fated"' }),
    ).toBeInTheDocument();
  });

  it("clicking a book title reopens metadata review in an overlay", async () => {
    setUpVoices();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1", title: "Fated" }), book({ id: "b2", title: "Cursed" })]}
        onChanged={() => {}}
      />,
    );
    await screen.findAllByText("Heart");

    await user.click(screen.getByRole("button", { name: /^📖 Fated/ }));

    expect(
      screen.getByRole("dialog", { name: 'Update "Fated"\'s info' }),
    ).toBeInTheDocument();
  });

  it("Start All Books calls startGeneration", async () => {
    setUpVoices();
    const startSpy = vi
      .spyOn(client, "startGeneration")
      .mockResolvedValue({ ok: true });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1" }), book({ id: "b2" })]}
        onChanged={onChanged}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Start All Books" }));

    expect(startSpy).toHaveBeenCalled();
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("has no axe violations in table mode", async () => {
    setUpVoices();
    const { container } = render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1" }), book({ id: "b2" })]}
        onChanged={() => {}}
      />,
    );
    await screen.findAllByText("Heart");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("single-book mode marks 'Choose Voice' current with this book trivially active", async () => {
    setUpVoices();
    render(
      <VoiceAssignmentScreen books={[book()]} lastVoice="af_heart" onChanged={() => {}} />,
    );
    await screen.findByText("Heart");

    expect(screen.getByText("Choose Voice").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(
      screen.getByRole("navigation", { name: "Progress" }),
    ).toHaveAttribute("aria-describedby");
  });

  it("table mode has no active book until a row is opened", async () => {
    setUpVoices();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1" }), book({ id: "b2", title: "Cursed" })]}
        onChanged={() => {}}
      />,
    );
    await screen.findAllByText("Heart");

    expect(
      screen.getByRole("navigation", { name: "Progress" }),
    ).not.toHaveAttribute("aria-describedby");
  });

  it("table mode's active book follows the most recently opened row", async () => {
    setUpVoices();
    const user = userEvent.setup();
    render(
      <VoiceAssignmentScreen
        books={[book({ id: "b1", title: "Fated" }), book({ id: "b2", title: "Cursed" })]}
        onChanged={() => {}}
      />,
    );
    await screen.findAllByText("Heart");

    await user.click(screen.getAllByRole("button", { name: "Change Voice" })[1]);

    const nav = screen.getByRole("navigation", { name: "Progress" });
    const describedById = nav.getAttribute("aria-describedby");
    expect(document.getElementById(describedById ?? "")).toHaveTextContent("Cursed");
  });
});
