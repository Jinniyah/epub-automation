import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import { WelcomeBack } from "./WelcomeBack";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Cursed.epub",
    status: "generating",
    ...overrides,
  };
}

describe("WelcomeBack", () => {
  it("shows the real title and a plain-language phase when status still knows the book", () => {
    render(
      <WelcomeBack
        pendingBookIds={["b1"]}
        books={[book({ title: "Cursed", status: "generating" })]}
        onContinue={() => {}}
        onNotNow={() => {}}
      />,
    );

    expect(screen.getByText(/Cursed/)).toBeInTheDocument();
    expect(screen.getByText(/getting the audio ready/)).toBeInTheDocument();
  });

  it("degrades to a plain count when the backend can't identify the pending books", () => {
    render(
      <WelcomeBack
        pendingBookIds={["b1", "b2"]}
        books={[]}
        onContinue={() => {}}
        onNotNow={() => {}}
      />,
    );

    expect(screen.getByText(/2 books you hadn't finished yet/)).toBeInTheDocument();
  });

  it("Continue and Not right now both fire their callbacks", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    const onNotNow = vi.fn();
    render(
      <WelcomeBack
        pendingBookIds={["b1"]}
        books={[book()]}
        onContinue={onContinue}
        onNotNow={onNotNow}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Not right now" }));

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onNotNow).toHaveBeenCalledTimes(1);
  });

  it("lists every pending book when more than one is known", () => {
    render(
      <WelcomeBack
        pendingBookIds={["b1", "b2"]}
        books={[
          book({ id: "b1", title: "Cursed", status: "generating" }),
          book({ id: "b2", title: "Fated", status: "voice_pick" }),
        ]}
        onContinue={() => {}}
        onNotNow={() => {}}
      />,
    );

    expect(screen.getByText(/Cursed/)).toBeInTheDocument();
    expect(screen.getByText(/Fated/)).toBeInTheDocument();
    expect(screen.getByText(/waiting on a voice choice/)).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <WelcomeBack
        pendingBookIds={["b1"]}
        books={[book({ title: "Cursed" })]}
        onContinue={() => {}}
        onNotNow={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
