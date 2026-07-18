import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { usePollingStatus } from "./hooks/usePollingStatus";
import {
  getSettings,
  getWelcomeBack,
  quitApp,
  resolveCollision,
} from "./api/client";
import type { Settings } from "./api/types";
import { AppHeader } from "./components/shared/AppHeader";
import { AddBooksScreen } from "./screens/AddBooksScreen";
import { AiHelperSetup } from "./screens/AiHelperSetup";
import { CollisionPrompt } from "./screens/CollisionPrompt";
import { ConfirmMetadataScreen } from "./screens/ConfirmMetadataScreen";
import { ErrorScreen } from "./screens/ErrorScreen";
import { FixInfoFlow } from "./screens/FixInfoFlow";
import { FoldersScreen } from "./screens/FoldersScreen";
import { MoreOptionsScreen } from "./screens/MoreOptionsScreen";
import { ReviewScreen } from "./screens/ReviewScreen";
import { VoiceAssignmentScreen } from "./screens/VoiceAssignmentScreen";
import { VoiceHistoryScreen } from "./screens/VoiceHistoryScreen";
import { WelcomeBack } from "./screens/WelcomeBack";
import { WordsScreen } from "./screens/WordsScreen";
import { WorkingScreen } from "./screens/WorkingScreen";

type Phase =
  | "loading"
  | "first-launch-folders"
  | "first-launch-ai"
  | "welcome-back"
  | "main"
  | "quit";

type SettingsSubView =
  | "menu"
  | "folders"
  | "words"
  | "ai-helper"
  | "voice-history"
  | null;

/** Top-level container: owns the one-time onboarding sequence (folder
 * setup -> AI Helper Setup -> "Welcome back") and, once past it, the
 * single `usePollingStatus()` every other screen is built from
 * (docs/design/PATTERNS.md §2's Container/Presentational split). Screen
 * routing for the main flow follows `01-architecture.md`'s state-
 * derivation precedence, with the client-side refinements each screen
 * needed once real (see the comments at each branch below for why).
 */
function App() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [pendingBookIds, setPendingBookIds] = useState<string[]>([]);
  const [subView, setSubView] = useState<SettingsSubView>(null);
  const [fixingBookId, setFixingBookId] = useState<string | null>(null);
  const polling = usePollingStatus();

  useEffect(() => {
    void (async () => {
      const s = await getSettings();
      setSettings(s);
      if (!s.books_folder || !s.output_folder) {
        setPhase("first-launch-folders");
        return;
      }
      const welcomeBack = await getWelcomeBack();
      if (welcomeBack.pending_book_ids.length > 0) {
        setPendingBookIds(welcomeBack.pending_book_ids);
        setPhase("welcome-back");
        return;
      }
      setPhase("main");
    })();
  }, []);

  async function refreshSettings() {
    setSettings(await getSettings());
  }

  /** Home only ever appears for the settings sub-views reached from
   * Screen 1's "More options" entry point -- never mid-onboarding
   * (nothing to go home to yet) and never mid-batch
   * (03-gui-ux-design.md's screens already *are* her true current
   * state; see `AppHeader`'s own docstring). */
  function renderScreen(): ReactNode {
    if (phase === "loading" || !settings) {
      return (
        <main>
          <p>Loading...</p>
        </main>
      );
    }

    if (phase === "first-launch-folders") {
      return (
        <FoldersScreen
          booksFolder={settings.books_folder}
          outputFolder={settings.output_folder}
          onDone={() => {
            void (async () => {
              const s = await getSettings();
              setSettings(s);
              setPhase(s.has_ai_api_key ? "main" : "first-launch-ai");
            })();
          }}
        />
      );
    }

    if (phase === "first-launch-ai") {
      return (
        <AiHelperSetup
          onDone={() => {
            void refreshSettings();
            setPhase("main");
          }}
        />
      );
    }

    if (phase === "welcome-back") {
      return (
        <WelcomeBack
          pendingBookIds={pendingBookIds}
          books={polling.status?.books ?? []}
          onContinue={() => setPhase("main")}
          onNotNow={() => setPhase("main")}
        />
      );
    }

    if (phase === "quit") {
      return (
        <main>
          <h1>You can close this window now.</h1>
        </main>
      );
    }

    // ---- "More options" hub + settings sub-views it opens, reached
    // from Screen 1's single "⚙️ More options" entry point ----
    if (subView === "menu") {
      return (
        <MoreOptionsScreen
          onOpenFolders={() => setSubView("folders")}
          onOpenWords={() => setSubView("words")}
          onOpenAiHelper={() => setSubView("ai-helper")}
          onOpenVoiceHistory={() => setSubView("voice-history")}
          onDone={() => setSubView(null)}
        />
      );
    }
    if (subView === "folders") {
      return (
        <FoldersScreen
          booksFolder={settings.books_folder}
          outputFolder={settings.output_folder}
          onDone={() => {
            void refreshSettings();
            setSubView(null);
          }}
        />
      );
    }
    if (subView === "words") {
      return (
        <WordsScreen
          words={settings.profanity_words}
          onDone={() => {
            void refreshSettings();
            setSubView(null);
          }}
        />
      );
    }
    if (subView === "ai-helper") {
      return (
        <AiHelperSetup
          onDone={() => {
            void refreshSettings();
            setSubView(null);
          }}
        />
      );
    }
    if (subView === "voice-history") {
      return <VoiceHistoryScreen onDone={() => setSubView(null)} />;
    }

    // ---- Main flow, driven by the polling status contract ----
    const status = polling.status;
    if (!status) {
      return (
        <main>
          <p>Loading...</p>
        </main>
      );
    }

    const onOpenMore = () => setSubView("menu");

    if (status.error) {
      const errorBook = status.books.find((b) => b.id === status.error?.book_id);
      return (
        <ErrorScreen
          summary={status.error.summary}
          bookId={status.error.book_id}
          bookLabel={errorBook?.title ?? errorBook?.original_filename}
          onBackToStart={() => void polling.refresh()}
          onRemoved={() => void polling.refresh()}
        />
      );
    }

    switch (status.state) {
      case "idle":
      case "done": {
        // "done" means the whole batch finished (01-architecture.md
        // §State derivation: "back to Screen 1") -- the old batch's
        // books stay in the server's snapshot until she adds a new one
        // (backend/app.py::_current_runner() resets lazily on the next
        // upload), so filter them out here rather than showing a stale
        // completed list on what should read as a fresh Screen 1.
        return (
          <AddBooksScreen
            books={status.books.filter((b) => b.status === "pending")}
            fixNames={settings.fix_names}
            cleanLanguage={settings.clean_language}
            onChanged={() => void polling.refresh()}
            onStart={() => void polling.refresh()}
            onOpenMore={onOpenMore}
          />
        );
      }

      case "identifying": {
        // The moment a single book is added it's already "pending", which
        // this same top-level state also covers (01-architecture.md) --
        // distinguishing "still on Screen 1, Start not pressed yet" from
        // "the identification loop is actually running" isn't something
        // the raw `state` field can do alone, so this checks the actual
        // per-book statuses, the same way useVoiceAssignmentView already
        // disambiguates single- vs. multi-book by inspecting `books`
        // directly rather than trusting `state` alone.
        const allPending =
          status.books.length > 0 && status.books.every((b) => b.status === "pending");
        if (allPending) {
          return (
            <AddBooksScreen
              books={status.books}
              fixNames={settings.fix_names}
              cleanLanguage={settings.clean_language}
              onChanged={() => void polling.refresh()}
              onStart={() => void polling.refresh()}
              onOpenMore={onOpenMore}
            />
          );
        }
        if (
          status.needs_input &&
          (status.needs_input.type === "confirm_metadata" ||
            status.needs_input.type === "ai_enrichment_failed")
        ) {
          const book = status.books.find((b) => b.id === status.needs_input?.book_id);
          if (book) {
            return (
              <ConfirmMetadataScreen
                book={book}
                enrichmentFailed={status.needs_input.type === "ai_enrichment_failed"}
                onConfirmed={() => void polling.refresh()}
                onRemoved={() => void polling.refresh()}
              />
            );
          }
        }
        // Rename/sanitize running automatically -- no screen needed
        // unless it needs her input (03-gui-ux-design.md §Per-book
        // identification loop).
        return (
          <main aria-labelledby="identifying-heading">
            <h1 id="identifying-heading" className="sr-only">
              Working
            </h1>
            <p>{status.message}</p>
          </main>
        );
      }

      case "voice_pick":
        return (
          <VoiceAssignmentScreen
            books={status.books}
            lastVoice={settings.last_voice}
            onChanged={() => void polling.refresh()}
          />
        );

      case "working": {
        if (
          status.needs_input?.type === "output_collision" &&
          status.needs_input.collision
        ) {
          const book = status.books.find((b) => b.id === status.needs_input?.book_id);
          if (book) {
            return (
              <CollisionPrompt
                bookTitle={book.title ?? book.original_filename}
                artifact={status.needs_input.collision.artifact}
                onChoice={(choice) =>
                  void resolveCollision(book.id, choice).then(() => polling.refresh())
                }
              />
            );
          }
        }
        return (
          <WorkingScreen
            books={status.books}
            activeBookId={status.active_book_id}
            message={status.message}
            onChanged={() => void polling.refresh()}
            onQuit={() => {
              void quitApp();
              setPhase("quit");
            }}
          />
        );
      }

      case "review": {
        const book = status.books.find((b) => b.id === status.active_book_id);
        if (!book) {
          return (
            <main>
              <p>{status.message}</p>
            </main>
          );
        }
        if (fixingBookId === book.id) {
          return (
            <FixInfoFlow
              book={book}
              onDone={() => {
                setFixingBookId(null);
                void polling.refresh();
              }}
              onCancel={() => setFixingBookId(null)}
            />
          );
        }
        return (
          <ReviewScreen
            book={book}
            onDone={() => void polling.refresh()}
            onFixIt={() => setFixingBookId(book.id)}
          />
        );
      }

      default:
        return null;
    }
  }

  const onHome = subView !== null ? () => setSubView(null) : undefined;

  /** "Quit for now" reachable from (almost) every screen, not just the
   * Working screen -- added after a real live incident: closing the tab
   * never stops the background server, and with no other way to end the
   * session, an already-running server from an earlier attempt got
   * mistaken for "already closed" (docs/BACKLOG.md Epic 10 Phase A).
   * Omitted during first-launch onboarding (`loading`/`first-launch-*`)
   * -- nothing meaningful is running yet -- and omitted specifically
   * when the plain `WorkingScreen` itself is what's rendered, since it
   * already has its own dedicated Quit button; `CollisionPrompt` (the
   * *other* thing `state: "working"` can mean) has no such button of its
   * own, so it still gets the header's. */
  const status = polling.status;
  const plainWorkingScreenActive =
    status?.state === "working" &&
    !(
      status.needs_input?.type === "output_collision" &&
      status.needs_input.collision &&
      status.books.some((b) => b.id === status.needs_input?.book_id)
    );
  const onHeaderQuit =
    (phase === "main" || phase === "welcome-back") && !plainWorkingScreenActive
      ? () => {
          void quitApp();
          setPhase("quit");
        }
      : undefined;

  return (
    <>
      <AppHeader onHome={onHome} onQuit={onHeaderQuit} />
      {renderScreen()}
    </>
  );
}

export default App;
