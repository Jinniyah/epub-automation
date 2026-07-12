import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getStatus } from "../api/client";
import type { StatusResponse } from "../api/types";

export interface PollingStatus {
  /** The most recently successful poll's response. `null` only before the
   * very first response arrives. */
  status: StatusResponse | null;
  /** True until the first response (success or failure) settles. */
  loading: boolean;
  /** Set when the most recent poll failed; `status` keeps its last-known
   * good value rather than being cleared, so a single dropped poll
   * doesn't blank the screen she's looking at. */
  error: ApiError | null;
  /** Re-poll immediately, outside the regular interval -- callers use
   * this right after a mutating action so the screen advances without
   * waiting for the next tick. */
  refresh: () => Promise<void>;
}

const DEFAULT_INTERVAL_MS = 3000;

/** Polls `GET /api/status` on an interval (03-gui-ux-design.md §Progress
 * reporting mechanism: "simple polling ... not WebSockets"). Every
 * screen that needs live batch state should consume this one hook's
 * output rather than polling independently (docs/design/PATTERNS.md §2's
 * Container/Presentational split -- one top-level container owns this).
 */
export function usePollingStatus(
  intervalMs: number = DEFAULT_INTERVAL_MS,
): PollingStatus {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const poll = useCallback(async () => {
    try {
      const next = await getStatus();
      if (!mountedRef.current) return;
      setStatus(next);
      setError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof ApiError ? err : new ApiError("Unknown error."));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const scheduleNext = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      void poll().then(() => {
        if (mountedRef.current) scheduleNext();
      });
    }, intervalMs);
  }, [poll, intervalMs]);

  useEffect(() => {
    mountedRef.current = true;
    void poll().then(() => {
      if (mountedRef.current) scheduleNext();
    });
    return () => {
      mountedRef.current = false;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [poll, scheduleNext]);

  const refresh = useCallback(async () => {
    await poll();
    if (mountedRef.current) scheduleNext();
  }, [poll, scheduleNext]);

  return { status, loading, error, refresh };
}
