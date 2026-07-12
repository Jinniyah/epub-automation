import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkingScreenView } from "./useWorkingScreenView";
import type { Book } from "../api/types";

function book(overrides: Partial<Book> = {}): Book {
  return {
    id: "b2",
    original_filename: "Cursed.epub",
    status: "generating",
    title: "Cursed",
    ...overrides,
  };
}

describe("useWorkingScreenView", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("computes the book index label from position in the batch", () => {
    const books = [
      book({ id: "b1", status: "complete" }),
      book({ id: "b2", progress: { chunks_done: 0, chunks_total: 10 } }),
      book({ id: "b3", status: "pending" }),
    ];
    const { result } = renderHook(() => useWorkingScreenView(books, "b2"));

    expect(result.current.bookIndexLabel).toBe("Book 2 of 3");
    expect(result.current.bookTitle).toBe("Cursed");
  });

  it("has no time estimate before enough chunks have completed", () => {
    const books = [book({ progress: { chunks_done: 1, chunks_total: 100 } })];
    const { result } = renderHook(() => useWorkingScreenView(books, "b2"));

    expect(result.current.timeEstimateText).toBeNull();
  });

  it("extrapolates a time estimate from observed throughput", () => {
    const books = [book({ progress: { chunks_done: 0, chunks_total: 100 } })];
    const { result, rerender } = renderHook(
      ({ b }: { b: Book[] }) => useWorkingScreenView(b, "b2"),
      { initialProps: { b: books } },
    );
    expect(result.current.timeEstimateText).toBeNull(); // establishes the start point

    // 10 chunks done in 10 seconds -> 1s/chunk -> 90 remaining -> 90s (~2 min)
    vi.setSystemTime(10_000);
    rerender({
      b: [book({ progress: { chunks_done: 10, chunks_total: 100 } })],
    });

    expect(result.current.timeEstimateText).toMatch(/more minute/);
  });

  it("resets its throughput tracking when the active book changes", () => {
    const { result, rerender } = renderHook(
      ({ id, b }: { id: string; b: Book[] }) => useWorkingScreenView(b, id),
      {
        initialProps: {
          id: "b2",
          b: [book({ progress: { chunks_done: 5, chunks_total: 100 } })],
        },
      },
    );
    vi.setSystemTime(10_000);
    rerender({
      id: "b2",
      b: [book({ progress: { chunks_done: 15, chunks_total: 100 } })],
    });
    expect(result.current.timeEstimateText).not.toBeNull();

    // A different book becomes active -- tracking must restart, not
    // treat this as instantaneous throughput from the old book's numbers.
    rerender({
      id: "b3",
      b: [
        book({ id: "b3", title: "Fated", progress: { chunks_done: 1, chunks_total: 50 } }),
      ],
    });

    expect(result.current.timeEstimateText).toBeNull();
    expect(result.current.bookTitle).toBe("Fated");
  });

  it("returns empty fields when nothing is active", () => {
    const { result } = renderHook(() => useWorkingScreenView([], null));
    expect(result.current.bookTitle).toBe("");
    expect(result.current.bookIndexLabel).toBe("");
    expect(result.current.timeEstimateText).toBeNull();
  });
});
