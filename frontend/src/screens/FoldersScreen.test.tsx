import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { FoldersScreen } from "./FoldersScreen";

describe("FoldersScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("Done is disabled until both folders are chosen", () => {
    render(<FoldersScreen booksFolder="" outputFolder="" onDone={() => {}} />);

    expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();
  });

  it("choosing a folder fills in the current-value caption", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "pickFolder").mockResolvedValue({ path: "C:\\Books" });
    render(<FoldersScreen booksFolder="" outputFolder="" onDone={() => {}} />);

    await user.click(
      screen.getByRole("button", { name: "Choose folder for your book files" }),
    );

    expect(screen.getByText((_, node) => node?.textContent === "Currently: C:\\Books")).toBeInTheDocument();
  });

  it("cancelling the native dialog (null path) leaves the value unchanged", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "pickFolder").mockResolvedValue({ path: null });
    render(
      <FoldersScreen
        booksFolder={"C:\\Books"}
        outputFolder=""
        onDone={() => {}}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Choose folder for your book files" }),
    );

    expect(screen.getByText((_, node) => node?.textContent === "Currently: C:\\Books")).toBeInTheDocument();
  });

  it("Done saves both folders and calls onDone", async () => {
    const user = userEvent.setup();
    const updateSpy = vi
      .spyOn(client, "updateSettings")
      .mockResolvedValue({ ok: true });
    const onDone = vi.fn();
    render(
      <FoldersScreen
        booksFolder={"C:\\Books"}
        outputFolder={"C:\\Audiobooks"}
        onDone={onDone}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Done" }));

    expect(updateSpy).toHaveBeenCalledWith({
      books_folder: "C:\\Books",
      output_folder: "C:\\Audiobooks",
    });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <FoldersScreen
        booksFolder={"C:\\Books"}
        outputFolder={"C:\\Audiobooks"}
        onDone={() => {}}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
