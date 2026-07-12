import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAriaLiveThrottled } from "./useAriaLiveThrottled";

describe("useAriaLiveThrottled", () => {
  it("announces the initial text immediately", () => {
    const { result } = renderHook(() => useAriaLiveThrottled("Add some books."));
    expect(result.current).toBe("Add some books.");
  });

  it("without progress, announces every text change", () => {
    const { result, rerender } = renderHook(
      ({ text }) => useAriaLiveThrottled(text),
      { initialProps: { text: "Finding out about your books..." } },
    );
    rerender({ text: "Take a look and let us know if it's right." });

    expect(result.current).toBe("Take a look and let us know if it's right.");
  });

  it("with progress, does not re-announce within the same 10% bucket", () => {
    const { result, rerender } = renderHook(
      ({ text, done }: { text: string; done: number }) =>
        useAriaLiveThrottled(text, { chunks_done: done, chunks_total: 100 }),
      { initialProps: { text: "About 10% done.", done: 10 } },
    );
    expect(result.current).toBe("About 10% done.");

    rerender({ text: "About 12% done.", done: 12 });

    // Still within the 10-19% bucket -- must not re-announce the churn.
    expect(result.current).toBe("About 10% done.");
  });

  it("re-announces once progress crosses into the next 10% bucket", () => {
    const { result, rerender } = renderHook(
      ({ text, done }: { text: string; done: number }) =>
        useAriaLiveThrottled(text, { chunks_done: done, chunks_total: 100 }),
      { initialProps: { text: "About 10% done.", done: 10 } },
    );

    rerender({ text: "About 20% done.", done: 20 });

    expect(result.current).toBe("About 20% done.");
  });

  it("always announces on completion even mid-bucket", () => {
    const { result, rerender } = renderHook(
      ({ text, done }: { text: string; done: number }) =>
        useAriaLiveThrottled(text, { chunks_done: done, chunks_total: 100 }),
      { initialProps: { text: "About 95% done.", done: 95 } },
    );

    rerender({ text: "All done!", done: 100 });

    expect(result.current).toBe("All done!");
  });
});
