import { useEffect, useRef, useState } from "react";
import type { BookProgress } from "../api/types";

function bucketOf(progress?: BookProgress | null): number | null {
  if (!progress || progress.chunks_total <= 0) return null;
  return Math.floor((progress.chunks_done / progress.chunks_total) * 10);
}

/** Gates how often a piece of status text is handed to an aria-live
 * region, so a screen-reader user gets the same "about 3 more hours"
 * update a sighted user glances at -- not a play-by-play of every poll
 * tick (03-gui-ux-design.md §Status updates for screen-reader users:
 * "Announce only on meaningful changes: a new book starting, roughly 10%
 * progress intervals, or completion").
 *
 * Callers render the *returned* value inside their `aria-live` element,
 * not `text` directly -- the throttling is entirely about which values
 * make it into that node, not a timer/debounce, since a screen reader
 * announces on DOM text change.
 */
export function useAriaLiveThrottled(
  text: string,
  progress?: BookProgress | null,
): string {
  const [announced, setAnnounced] = useState(text);
  const lastBucketRef = useRef<number | null>(bucketOf(progress));
  const lastTextRef = useRef(text);

  const bucket = bucketOf(progress);
  const isComplete = Boolean(
    progress && progress.chunks_total > 0 && progress.chunks_done >= progress.chunks_total,
  );

  useEffect(() => {
    const bucketChanged = bucket !== null && bucket !== lastBucketRef.current;
    // With no progress to bucket by (e.g. the identification/review
    // screens), every real message change is already a meaningful one --
    // a new book starting, an error, etc. -- so nothing extra to throttle.
    const plainTextChanged = bucket === null && text !== lastTextRef.current;

    if (bucketChanged || plainTextChanged || isComplete) {
      lastBucketRef.current = bucket;
      lastTextRef.current = text;
      setAnnounced(text);
    }
  }, [text, bucket, isComplete]);

  return announced;
}
