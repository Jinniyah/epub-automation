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
 */
export function AppHeader({ onHome }: AppHeaderProps) {
  return (
    <header className="app-header">
      <p className="app-header__brand">📚 Audiobook Maker</p>
      {onHome ? (
        <button type="button" className="link-button" onClick={onHome}>
          🏠 Home
        </button>
      ) : null}
    </header>
  );
}
