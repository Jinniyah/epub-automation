import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { VoiceAssignmentScreen } from "./VoiceAssignmentScreen";
import type { Book } from "../api/types";

const VOICES = [
  { key: "af_heart", name: "Heart" },
  { key: "bm_george", name: "George" },
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

    await user.click(screen.getByRole("button", { name: /Fated/ }));

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
});
