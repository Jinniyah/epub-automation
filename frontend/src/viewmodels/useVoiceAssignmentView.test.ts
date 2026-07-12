import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useVoiceAssignmentView } from "./useVoiceAssignmentView";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b1",
    original_filename: "Fated.epub",
    status: "voice_pick",
    ...overrides,
  };
}

describe("useVoiceAssignmentView", () => {
  it("is single mode for exactly one voice_pick book", () => {
    const { result } = renderHook(() => useVoiceAssignmentView([book()]));
    expect(result.current.mode).toBe("single");
    expect(result.current.rows).toHaveLength(1);
  });

  it("is table mode for more than one voice_pick book", () => {
    const { result } = renderHook(() =>
      useVoiceAssignmentView([book({ id: "b1" }), book({ id: "b2" })]),
    );
    expect(result.current.mode).toBe("table");
    expect(result.current.rows).toHaveLength(2);
  });

  it("only includes books actually at voice_pick", () => {
    const { result } = renderHook(() =>
      useVoiceAssignmentView([book({ id: "b1" }), book({ id: "b2", status: "complete" })]),
    );
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].bookId).toBe("b1");
  });

  it("combines author as Last, First and series with its number", () => {
    const { result } = renderHook(() =>
      useVoiceAssignmentView([
        book({
          title: "Fated",
          author_first: "Benedict",
          author_last: "Jacka",
          series: "Alex Verus",
          series_number: "1",
          voice: "am_george",
        }),
      ]),
    );

    expect(result.current.rows[0]).toEqual({
      bookId: "b1",
      title: "Fated",
      author: "Jacka, Benedict",
      series: "Alex Verus #1",
      voice: "am_george",
    });
  });

  it("falls back to the original filename when no title is known yet", () => {
    const { result } = renderHook(() =>
      useVoiceAssignmentView([book({ title: undefined })]),
    );
    expect(result.current.rows[0].title).toBe("Fated.epub");
  });
});
