// API-client facade: the one module that knows the Flask JSON API's
// URLs and shapes (docs/design/PATTERNS.md §2 "API-client facade").
// Every call is a relative /api/... path -- never an absolute
// http://127.0.0.1:<port> URL -- so the Vite dev proxy (vite.config.ts)
// is the only place that needs to know the backend's actual port
// (frontend/README.md).
import type {
  AddBooksResponse,
  ApiResult,
  DiskSpaceReport,
  FolderPickResult,
  MetadataCorrections,
  OkResponse,
  Settings,
  SettingsUpdate,
  StatusResponse,
  SupportBundleResponse,
  VoiceHistoryEntry,
  VoicesResponse,
  WelcomeBackResponse,
} from "./types";

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("Could not reach the app's background service.", undefined);
  }

  let body: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError("Got an unreadable response from the app.", response.status);
    }
  }

  // Every route in the API reference returns a JSON body even on
  // failure ({ok:false, error}) except the few that intentionally
  // return non-JSON (voice sample audio, handled by its own helper
  // below, never through this function). A non-2xx with no body at all
  // is the one genuinely unexpected case.
  if (!response.ok && body === null) {
    throw new ApiError(`Request failed (${response.status}).`, response.status);
  }

  return body as T;
}

function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------------

export function getStatus(): Promise<StatusResponse> {
  return getJson<StatusResponse>("/api/status");
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export function getSettings(): Promise<Settings> {
  return getJson<Settings>("/api/settings");
}

export function updateSettings(update: SettingsUpdate): Promise<OkResponse> {
  return postJson<OkResponse>("/api/settings", update);
}

// ---------------------------------------------------------------------------
// Native folder picker
// ---------------------------------------------------------------------------

/** "📂 See the audiobook files" (03-gui-ux-design.md §Screen: Review) --
 * opens this book's own output subfolder in File Explorer. No path ever
 * crosses the wire; the backend resolves it from the book's own
 * already-tracked data. `ok: false` (not a thrown error) if it no
 * longer exists. */
export function openBookFolder(
  bookId: string,
): Promise<{ ok: boolean; error?: string }> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/open-folder`);
}

/** "📂 See all my finished books" -- opens her remembered
 * `output_folder`. */
export function openOutputFolder(): Promise<{ ok: boolean; error?: string }> {
  return postJson("/api/open-output-folder");
}

export function pickFolder(options?: {
  title?: string;
  initialDir?: string;
}): Promise<FolderPickResult> {
  return postJson<FolderPickResult>("/api/dialogs/folder", {
    title: options?.title ?? "",
    initial_dir: options?.initialDir ?? "",
  });
}

// ---------------------------------------------------------------------------
// Screen 1: Add Books
// ---------------------------------------------------------------------------

export function addBooks(files: File[]): Promise<AddBooksResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  return request<AddBooksResponse>("/api/books", { method: "POST", body: form });
}

export function removeBook(bookId: string): Promise<OkResponse> {
  return del<OkResponse>(`/api/books/${encodeURIComponent(bookId)}`);
}

export function getDiskSpace(): Promise<DiskSpaceReport> {
  return getJson<DiskSpaceReport>("/api/disk-space");
}

// ---------------------------------------------------------------------------
// Batch lifecycle
// ---------------------------------------------------------------------------

export function startBatch(): Promise<OkResponse> {
  return postJson<OkResponse>("/api/batch/start");
}

export function startGeneration(): Promise<OkResponse> {
  return postJson<OkResponse>("/api/batch/start-generation");
}

// ---------------------------------------------------------------------------
// Per-book identification loop
// ---------------------------------------------------------------------------

export function confirmMetadata(
  bookId: string,
  corrections: MetadataCorrections | null,
): Promise<ApiResult<{ status: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/confirm`, {
    corrections,
  });
}

// ---------------------------------------------------------------------------
// Voice assignment
// ---------------------------------------------------------------------------

export function getVoices(): Promise<VoicesResponse> {
  return getJson<VoicesResponse>("/api/voices");
}

export function voiceSampleUrl(voiceKey: string): string {
  return `/api/voice-samples/${encodeURIComponent(voiceKey)}`;
}

export function assignVoice(
  bookId: string,
  voice: string,
): Promise<ApiResult<{ voice: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/voice`, { voice });
}

/** Corrects title/author/series while a book sits at `voice_pick` -- the
 * multi-book voice table's clickable book title (03-gui-ux-design.md
 * §Voice assignment). Distinct from `confirmMetadata` (identification
 * loop only) and `retagBook` (already-generated files on disk). */
export function updateBookMetadata(
  bookId: string,
  corrections: MetadataCorrections,
): Promise<ApiResult<{ status: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/metadata`, {
    corrections,
  });
}

// ---------------------------------------------------------------------------
// Pause / Cancel
// ---------------------------------------------------------------------------

export function pauseBook(bookId: string): Promise<OkResponse> {
  return postJson<OkResponse>(`/api/books/${encodeURIComponent(bookId)}/pause`);
}

export function cancelBook(
  bookId: string,
  keepPartial = true,
): Promise<OkResponse & { status: string }> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/cancel`, {
    keep_partial: keepPartial,
  });
}

// ---------------------------------------------------------------------------
// Output collision
// ---------------------------------------------------------------------------

export function resolveCollision(
  bookId: string,
  choice: "replace" | "keep_both",
): Promise<ApiResult<{ status: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/collision`, { choice });
}

// ---------------------------------------------------------------------------
// Review + "No, let me fix it"
// ---------------------------------------------------------------------------

export function submitReview(
  bookId: string,
  looksGood: boolean,
): Promise<ApiResult<{ status: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/review`, {
    looks_good: looksGood,
  });
}

export function retagBook(
  bookId: string,
  overrides: MetadataCorrections,
): Promise<ApiResult<{ status: string }>> {
  return postJson(`/api/books/${encodeURIComponent(bookId)}/retag`, { overrides });
}

// ---------------------------------------------------------------------------
// "What voice did I use before?"
// ---------------------------------------------------------------------------

export function getVoiceHistory(): Promise<
  ApiResult<{ history: VoiceHistoryEntry[] }>
> {
  return getJson("/api/voice-history");
}

// ---------------------------------------------------------------------------
// Error communication
// ---------------------------------------------------------------------------

export function requestSupportBundle(
  technicalError?: string,
): Promise<SupportBundleResponse> {
  return postJson<SupportBundleResponse>("/api/support-bundle", {
    technical_error: technicalError,
  });
}

// ---------------------------------------------------------------------------
// "Welcome back"
// ---------------------------------------------------------------------------

export function getWelcomeBack(): Promise<WelcomeBackResponse> {
  return getJson<WelcomeBackResponse>("/api/welcome-back");
}

/** "⚙️ More options" -> "clean up stuck in-progress state"
 * (docs/BACKLOG.md Epic 9) -- a blunt, confirm-gated full reset of
 * pending-book tracking and the `Library/*` staging folders, for when
 * "Welcome back" can't resume (the source files are already gone) or
 * she just doesn't want it to. */
export function cleanupInProgress(): Promise<OkResponse> {
  return postJson<OkResponse>("/api/cleanup-in-progress");
}

// ---------------------------------------------------------------------------
// Quit
// ---------------------------------------------------------------------------

export function quitApp(): Promise<OkResponse> {
  return postJson<OkResponse>("/api/quit");
}
