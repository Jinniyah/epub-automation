import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  addBooks,
  assignVoice,
  cancelBook,
  confirmMetadata,
  getDiskSpace,
  getSettings,
  getStatus,
  getVoiceHistory,
  getVoices,
  getWelcomeBack,
  openBookFolder,
  openOutputFolder,
  pauseBook,
  pickFolder,
  quitApp,
  removeBook,
  requestSupportBundle,
  resolveCollision,
  retagBook,
  startBatch,
  startGeneration,
  submitReview,
  updateBookMetadata,
  updateSettings,
  voiceSampleUrl,
} from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getStatus calls GET /api/status and returns the parsed body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ state: "idle", books: [] }));

    const result = await getStatus();

    expect(fetchMock).toHaveBeenCalledWith("/api/status", undefined);
    expect(result.state).toBe("idle");
  });

  it("updateSettings POSTs JSON with the right content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await updateSettings({ books_folder: "C:\\Books" });

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/settings");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ books_folder: "C:\\Books" });
  });

  it("removeBook issues a DELETE to the book's own URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await removeBook("b1");

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/books/b1");
    expect(init.method).toBe("DELETE");
  });

  it("addBooks sends a multipart form with a files field per file", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    const file = new File(["epub bytes"], "Fated.epub");

    await addBooks([file]);

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/books");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).getAll("files")).toHaveLength(1);
  });

  it("surfaces a 409/400-style ok:false body instead of throwing", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: false, error: "not ready" }, 409));

    const result = await assignVoice("b1", "af_heart");

    expect(result.ok).toBe(false);
  });

  it("throws ApiError when fetch itself rejects (network failure)", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    await expect(getStatus()).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError on a non-2xx response with no JSON body at all", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));

    await expect(getStatus()).rejects.toMatchObject({ status: 500 });
  });

  it("throws ApiError when the response body isn't valid JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>not json</html>", { status: 200 }));

    await expect(getStatus()).rejects.toBeInstanceOf(ApiError);
  });

  it("voiceSampleUrl builds a URL-encoded per-voice path", () => {
    expect(voiceSampleUrl("af_heart")).toBe("/api/voice-samples/af_heart");
  });

  it("getSettings issues a plain GET with no body", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ schema_version: 1, has_ai_api_key: false }),
    );

    await getSettings();

    expect(fetchMock).toHaveBeenCalledWith("/api/settings", undefined);
  });

  it("every remaining thin wrapper hits its documented route", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));

    await confirmMetadata("b1", { title: "New" });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/confirm",
      expect.objectContaining({ method: "POST" }),
    );

    await getVoices();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/voices", undefined);

    await updateBookMetadata("b1", { title: "New" });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/metadata",
      expect.objectContaining({ method: "POST" }),
    );

    await pauseBook("b1");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/pause",
      expect.objectContaining({ method: "POST" }),
    );

    await cancelBook("b1", false);
    const [, cancelInit] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(JSON.parse(cancelInit.body as string)).toEqual({ keep_partial: false });

    await resolveCollision("b1", "replace");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/collision",
      expect.objectContaining({ method: "POST" }),
    );

    await submitReview("b1", true);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/review",
      expect.objectContaining({ method: "POST" }),
    );

    await retagBook("b1", { title: "New" });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/retag",
      expect.objectContaining({ method: "POST" }),
    );

    await getVoiceHistory();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/voice-history", undefined);

    await requestSupportBundle("boom");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/support-bundle",
      expect.objectContaining({ method: "POST" }),
    );

    await getWelcomeBack();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/welcome-back", undefined);

    await quitApp();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/quit",
      expect.objectContaining({ method: "POST" }),
    );

    await getDiskSpace();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/disk-space", undefined);

    await startBatch();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/batch/start",
      expect.objectContaining({ method: "POST" }),
    );

    await startGeneration();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/batch/start-generation",
      expect.objectContaining({ method: "POST" }),
    );

    await openBookFolder("b1");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/books/b1/open-folder",
      expect.objectContaining({ method: "POST" }),
    );

    await openOutputFolder();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/open-output-folder",
      expect.objectContaining({ method: "POST" }),
    );

    await pickFolder({ title: "Pick one", initialDir: "C:\\Books" });
    const [, pickInit] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(JSON.parse(pickInit.body as string)).toEqual({
      title: "Pick one",
      initial_dir: "C:\\Books",
    });
  });

  it("pickFolder defaults title/initialDir to empty strings when omitted", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ path: null }));

    await pickFolder();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      title: "",
      initial_dir: "",
    });
  });
});
