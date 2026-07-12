import { useRef } from "react";
import type { Book } from "../api/types";

export interface WorkingScreenView {
  bookTitle: string;
  /** e.g. "Book 1 of 3". */
  bookIndexLabel: string;
  /** `null` before enough chunks have completed to extrapolate from --
   * callers should fall back to the friendly status line alone
   * (03-gui-ux-design.md §Screen: Working). */
  timeEstimateText: string | null;
  progress: Book["progress"];
}

const MIN_CHUNKS_TO_ESTIMATE = 2;

function formatRemaining(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "Almost done";
  if (minutes === 1) return "About 1 more minute";
  if (minutes < 60) return `About ${minutes} more minutes`;
  const hours = Math.round(minutes / 60);
  return hours === 1 ? "About 1 more hour" : `About ${hours} more hours`;
}

/** Drives §Screen: Working (03-gui-ux-design.md). The time estimate is
 * derived from throughput actually observed *in this job* -- chunks
 * completed so far vs. wall-clock time elapsed since generation for
 * this book started -- not a hardcoded guess (the same reasoning
 * `pipeline/tts_engine.py::SECONDS_PER_CHAR` uses server-side for the
 * disk-space estimate, computed here instead since the polling contract
 * doesn't carry timestamps). Tracked entirely client-side: a ref keyed
 * by book id remembers when this hook first saw that book generating,
 * reset automatically when a different book becomes active.
 */
export function useWorkingScreenView(
  books: Book[],
  activeBookId: string | null,
): WorkingScreenView {
  const startRef = useRef<{ bookId: string; at: number; chunksDone: number } | null>(
    null,
  );

  const activeIndex = books.findIndex((b) => b.id === activeBookId);
  const activeBook = activeIndex >= 0 ? books[activeIndex] : undefined;
  const progress = activeBook?.progress;

  if (!activeBook || !progress) {
    startRef.current = null;
    return {
      bookTitle: activeBook?.title ?? activeBook?.original_filename ?? "",
      bookIndexLabel:
        activeIndex >= 0 ? `Book ${activeIndex + 1} of ${books.length}` : "",
      timeEstimateText: null,
      progress: undefined,
    };
  }

  if (startRef.current?.bookId !== activeBook.id) {
    startRef.current = {
      bookId: activeBook.id,
      at: Date.now(),
      chunksDone: progress.chunks_done,
    };
  }

  const elapsedMs = Date.now() - startRef.current.at;
  const chunksSinceStart = progress.chunks_done - startRef.current.chunksDone;
  const remainingChunks = progress.chunks_total - progress.chunks_done;

  let timeEstimateText: string | null = null;
  if (chunksSinceStart >= MIN_CHUNKS_TO_ESTIMATE && elapsedMs > 0 && remainingChunks > 0) {
    const msPerChunk = elapsedMs / chunksSinceStart;
    timeEstimateText = formatRemaining(remainingChunks * msPerChunk);
  }

  return {
    bookTitle: activeBook.title ?? activeBook.original_filename,
    bookIndexLabel: `Book ${activeIndex + 1} of ${books.length}`,
    timeEstimateText,
    progress,
  };
}
