import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePollingStatus } from "./usePollingStatus";
import type { StatusResponse } from "../api/types";

function statusResponse(overrides: Partial<StatusResponse> = {}): StatusResponse {
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

describe("usePollingStatus", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("polls immediately on mount and reports loading:false after", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(statusResponse()), { status: 200 }),
    );
    const { result } = renderHook(() => usePollingStatus(5000));

    expect(result.current.loading).toBe(true);

    await vi.waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.status?.state).toBe("idle");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("polls again after the interval elapses", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(statusResponse()), { status: 200 }),
    );
    renderHook(() => usePollingStatus(5000));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the last-known status when a poll fails, and surfaces the error", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify(statusResponse({ state: "identifying" })), {
          status: 200,
        }),
      )
      .mockRejectedValueOnce(new TypeError("network down"));

    const { result } = renderHook(() => usePollingStatus(5000));
    await vi.waitFor(() => expect(result.current.status?.state).toBe("identifying"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.status?.state).toBe("identifying");
  });

  it("refresh() re-polls immediately without waiting for the interval", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(statusResponse()), { status: 200 }),
    );
    const { result } = renderHook(() => usePollingStatus(60_000));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.refresh();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops polling after unmount", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(statusResponse()), { status: 200 }),
    );
    const { unmount } = renderHook(() => usePollingStatus(5000));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    unmount();
    const callsAtUnmount = fetchMock.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });

    expect(fetchMock.mock.calls.length).toBe(callsAtUnmount);
  });
});
