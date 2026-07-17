export interface AppHeaderProps {
  /** Only provided when going Home is actually safe -- mid-batch
   * (identifying/voice-pick/working/review) the screen she's on already
   * *is* her true current state, so there's nowhere safer to send her
   * without either misrepresenting that state or implying she's
   * abandoning in-progress work. Real navigation only, never a Cancel
   * in disguise. */
  onHome?: () => void;
}

/** A real `<header>` landmark on every screen, distinct from `<main>`
 * (03-gui-ux-design.md §Robust: "a page <header> ... so a screen-reader
 * user can jump between sections") -- also makes it obvious at a glance
 * which app/screen she's looking at, per real user feedback.
 *
 * **Redesigned 2026-07-14 (real user feedback):** the brand text and
 * Home button used to float directly on the page background, outside
 * any bounded shape -- the title read as small and stray, and the Home
 * button (a muted, low-contrast link) was genuinely easy to miss
 * entirely. This version gives the header its own card (same surface
 * language `main` already uses), a proper wordmark treatment (icon
 * badge + bold text), and a Home button with real, high-contrast chrome
 * -- a filled pill, not a blend-into-the-background link -- so both
 * problems are fixed the same way: give both elements a real, visible
 * home to live in.
 */
export function AppHeader({ onHome }: AppHeaderProps) {
  return (
    <header className="app-header">
      <p className="app-header__brand">
        <span className="icon-badge app-header__icon" aria-hidden="true">
          📚
        </span>
        Audiobook Maker
      </p>
      {onHome ? (
        <button type="button" className="app-header__home" onClick={onHome}>
          🏠 Home
        </button>
      ) : null}
    </header>
  );
}
