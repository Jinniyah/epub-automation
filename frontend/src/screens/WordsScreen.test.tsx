import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { WordsScreen } from "./WordsScreen";

describe("WordsScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the existing words with a Remove button each", () => {
    render(<WordsScreen words={["darn", "heck"]} onDone={() => {}} />);

    expect(screen.getByText("darn")).toBeInTheDocument();
    expect(screen.getByText("heck")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2);
  });

  it("Remove sends the whole updated array back", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    render(<WordsScreen words={["darn", "heck"]} onDone={() => {}} />);

    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);

    expect(updateSpy).toHaveBeenCalledWith({ profanity_words: ["heck"] });
    expect(screen.queryByText("darn")).not.toBeInTheDocument();
  });

  it("Add is disabled for a blank word, and sends the appended array", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    render(<WordsScreen words={["darn"]} onDone={() => {}} />);

    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();

    await user.type(screen.getByLabelText("Add a new word"), "shoot");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(updateSpy).toHaveBeenCalledWith({ profanity_words: ["darn", "shoot"] });
    expect(screen.getByText("shoot")).toBeInTheDocument();
  });

  it("Done fires its callback", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    render(<WordsScreen words={[]} onDone={onDone} />);

    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <WordsScreen words={["darn", "heck"]} onDone={() => {}} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
