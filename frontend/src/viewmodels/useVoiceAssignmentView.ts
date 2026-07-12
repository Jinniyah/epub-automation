import type { Book } from "../api/types";
import { formatAuthor } from "../utils/authorName";

export interface VoiceAssignmentRow {
  bookId: string;
  title: string;
  author?: string;
  series?: string;
  voice: string;
}

export interface VoiceAssignmentView {
  /** Single-book vs. multi-book table is the same top-level `state`
   * value ("voice_pick"), disambiguated purely by book count
   * (01-architecture.md §State derivation) -- this hook is the one
   * place that disambiguation happens, so screens never re-derive it. */
  mode: "single" | "table";
  rows: VoiceAssignmentRow[];
}

/** View-model for §Voice assignment (03-gui-ux-design.md). Every row's
 * `voice` is already the right starting value to display -- `pipeline/
 * batch_runner.py::_maybe_enter_voice_pick()` pre-fills every book with
 * her single global last-used voice the moment it reaches `voice_pick`,
 * before this ever runs.
 *
 * **Scope decision (Epic 8):** the spec's "two or more books in this
 * batch share a series get the same voice as each other" same-series
 * default is *not* reproduced client-side here. The backend only ever
 * hands out one single global default (see the function above) -- CLAUDE.md's
 * own flagged-open-item for this named the single-global-default case as
 * likely "already satisfy[ing] 03-gui-ux-design.md's intent" once this
 * screen was real, and building a second, client-only notion of the
 * "current" default that can silently disagree with what the server
 * already assigned is worse than the marginal series-grouping
 * convenience it would buy. "Change Voice" already covers giving
 * specific books a different voice either way.
 */
export function useVoiceAssignmentView(books: Book[]): VoiceAssignmentView {
  const rows: VoiceAssignmentRow[] = books
    .filter((b) => b.status === "voice_pick")
    .map((b) => ({
      bookId: b.id,
      title: b.title ?? b.original_filename,
      author: formatAuthor(b.author_first, b.author_last) || undefined,
      series: b.series
        ? b.series_number
          ? `${b.series} #${b.series_number}`
          : b.series
        : undefined,
      voice: b.voice ?? "",
    }));

  return { mode: rows.length === 1 ? "single" : "table", rows };
}
