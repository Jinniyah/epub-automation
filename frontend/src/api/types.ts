// Types for the JSON API contract in docs/requirements/01-architecture.md
// §Status endpoint contract and §Full API route reference. Keep these in
// sync with backend/bridge.py / backend/app.py -- this file has no
// runtime behavior of its own, it's the typed mirror of the wire shape.

export type BatchState =
  | "idle"
  | "identifying"
  | "voice_pick"
  | "working"
  | "review"
  | "done"
  | "error";

export type BookStatus =
  | "pending"
  | "identifying"
  | "needs_input"
  | "identified"
  | "voice_pick"
  | "generating"
  | "paused"
  | "complete"
  | "cancelled"
  | "error";

export type NeedsInputType =
  | "confirm_metadata"
  | "ai_enrichment_failed"
  | "pick_voice"
  | "review_result"
  | "output_collision";

export interface CollisionDetail {
  artifact: "epub" | "audiobook";
  path: string;
}

export interface NeedsInput {
  book_id: string;
  type: NeedsInputType;
  collision?: CollisionDetail;
}

export interface BookProgress {
  chunks_done: number;
  chunks_total: number;
}

export interface Book {
  id: string;
  original_filename: string;
  status: BookStatus;
  title?: string;
  author_first?: string;
  author_last?: string;
  series?: string;
  series_number?: string;
  voice?: string;
  progress?: BookProgress;
}

export interface ErrorInfo {
  book_id: string | null;
  summary: string;
  support_bundle_available: boolean;
}

export interface StatusResponse {
  state: BatchState;
  active_book_id: string | null;
  message: string;
  needs_input: NeedsInput | null;
  books: Book[];
  error: ErrorInfo | null;
}

export type AiProvider = "gemini" | "openai" | "none";

export interface Settings {
  schema_version: number;
  books_folder: string;
  output_folder: string;
  fix_names: boolean;
  clean_language: boolean;
  ai_provider: AiProvider;
  has_ai_api_key: boolean;
  last_voice: string;
  profanity_words: string[];
}

export type SettingsUpdate = Partial<
  Omit<Settings, "schema_version" | "has_ai_api_key"> & { ai_api_key: string }
>;

export interface FolderPickResult {
  path: string | null;
}

export type BookRejectionReason =
  | "not_epub"
  | "damaged"
  | "drm_protected"
  | "max_files_exceeded";

export interface AddBookResult {
  ok: boolean;
  original_filename: string;
  book_id: string | null;
  reason: BookRejectionReason | null;
  message: string | null;
}

export interface AddBooksResponse {
  results: AddBookResult[];
}

export interface DiskSpaceCheckedPath {
  path: string;
  free_bytes: number;
  sufficient: boolean;
}

export interface DiskSpaceReport {
  estimated_total_bytes: number;
  any_insufficient: boolean;
  checked_paths: DiskSpaceCheckedPath[];
}

export interface MetadataCorrections {
  title?: string;
  author_first?: string;
  author_last?: string;
  series?: string;
  series_number?: string;
}

export interface VoiceChoice {
  key: string;
  name: string;
}

export interface VoicesResponse {
  voices: VoiceChoice[];
}

export type CollisionChoice = "replace" | "keep_both";

export interface VoiceHistoryEntry {
  label: string;
  voice: string;
}

export interface SupportBundleResponse {
  ok: true;
  path: string;
}

export interface WelcomeBackResponse {
  pending_book_ids: string[];
}

// The uniform "ok" envelope most mutating routes use, per
// 01-architecture.md: "A mutating route's JSON success body always
// includes `ok: true`; a failure is a non-2xx status with
// `{ok: false, error: "..."}`" -- POST /api/books is the one documented
// exception (AddBooksResponse above has its own per-file shape).
export interface OkResponse {
  ok: true;
  [key: string]: unknown;
}

export interface ErrResponse {
  ok: false;
  error: string;
}

export type ApiResult<T extends object> = (OkResponse & T) | ErrResponse;
