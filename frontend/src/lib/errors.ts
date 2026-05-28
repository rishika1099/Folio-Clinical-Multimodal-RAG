/**
 * Map raw errors (Error objects, fetch failures, HTTP status strings) to
 * plain-English messages a non-technical user can act on.
 *
 * Used everywhere a setError(...) is called. Keep the messages short and
 * actionable — what happened, what to try next.
 */
export function friendlyError(e: unknown): string {
  const raw = (e as any)?.message || String(e || "");

  // 1) Auth-flow shortcut. The auth guard already handles redirect; the
  //    chat UI sometimes shows the error briefly.
  if (raw === "unauthorized") return "You've been signed out. Please log in again.";

  // 2) Network / fetch failed (offline, DNS, CORS without preflight, …).
  if (raw === "Failed to fetch" || raw === "Load failed" || raw.includes("NetworkError") ||
      raw.includes("ERR_NETWORK") || raw.includes("ERR_INTERNET_DISCONNECTED")) {
    return "Couldn't reach Folio. Check your internet connection and try again.";
  }
  if (raw.includes("AbortError") || raw === "The user aborted a request.") {
    return "Request was cancelled.";
  }

  // 3) HTTP status prefix from api.ts (we throw `${status} ${body}`).
  const statusMatch = raw.match(/^(\d{3})\b/);
  const status = statusMatch ? Number(statusMatch[1]) : null;
  let body = statusMatch ? raw.slice(statusMatch[0].length).trim() : raw;

  // FastAPI returns `{"detail": "..."}` or `{"detail": {message: "...", ...}}`.
  // Try to extract the inner human message; fall back to the raw body.
  if (body.startsWith("{")) {
    try {
      const parsed = JSON.parse(body);
      if (parsed?.detail) {
        if (typeof parsed.detail === "string") body = parsed.detail;
        else if (typeof parsed.detail?.message === "string") body = parsed.detail.message;
      }
    } catch { /* fall through with raw body */ }
  }

  if (status === 400) return body || "That doesn't look right — please double-check what you entered.";
  if (status === 401 || status === 403) return "You've been signed out. Please log in again.";
  if (status === 404) return "We couldn't find that — it may have been deleted.";
  if (status === 409) return body || "That username is already taken — try another.";
  if (status === 413) return "That file is too large. Try a smaller PDF or image.";
  if (status === 415) return "We can't read that file format. Try a PDF, image, or audio file.";
  if (status === 422) return body || "Some of the information looks invalid — please check it.";
  // 429 from our rate-limit module already carries a friendly message — use it.
  if (status === 429) return body || "Folio is at capacity right now. Please try again in a minute or two.";
  if (status === 500) return "Something went wrong on our side. Try again in a moment.";
  if (status === 502 || status === 503 || status === 504) {
    return "Folio is warming up — give it 30 seconds and try again.";
  }

  // 4) Streaming / SSE-specific
  if (raw.includes("SSE failed")) return "Lost connection while streaming. Please try again.";

  // 5) LLM / pipeline messages bubbled up
  if (/Extraction failed/i.test(raw)) return "Couldn't read that report. Try again, or paste the text directly.";
  if (/Could not parse model JSON/i.test(raw)) return "Couldn't parse the report — please try again.";
  if (/empty file/i.test(raw)) return "That file looked empty. Please try a different one.";
  if (/Could not extract any text from PDF/i.test(raw)) return "We couldn't read any text from that PDF. If it's a scan, try uploading as a photo instead.";

  // 6) Provider key errors (shouldn't surface in prod, but be friendly).
  if (/api[_-]?key/i.test(raw)) return "Folio's AI services are temporarily unavailable. Please try again later.";

  // 7) Fallback — show the raw message if it's already humanish (under 120 chars
  //    and no stack-trace cruft); otherwise a generic apology.
  if (body && body.length < 120 && !/^\{|<html/i.test(body)) return body;
  return "Something went wrong. Please try again.";
}
