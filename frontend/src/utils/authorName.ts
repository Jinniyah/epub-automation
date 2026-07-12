/** The app displays/edits author name as one combined "Last, First" field
 * everywhere she sees it (03-gui-ux-design.md's mockups: "Author: Jacka,
 * Benedict"), matching the same convention already used for display
 * throughout the pipeline (audit log, rename stage) -- but the API and
 * data model keep `author_first`/`author_last` split
 * (01-architecture.md's status contract). These two functions are the
 * one place that combined string gets parsed back apart, so every
 * screen that edits an author name does it the same way.
 */

export function formatAuthor(authorFirst?: string, authorLast?: string): string {
  const first = authorFirst?.trim() ?? "";
  const last = authorLast?.trim() ?? "";
  if (last && first) return `${last}, ${first}`;
  return last || first;
}

export function parseAuthor(display: string): {
  author_first: string;
  author_last: string;
} {
  const commaIndex = display.indexOf(",");
  if (commaIndex === -1) {
    return { author_first: "", author_last: display.trim() };
  }
  return {
    author_last: display.slice(0, commaIndex).trim(),
    author_first: display.slice(commaIndex + 1).trim(),
  };
}
