/**
 * Minimal SSE consumer over fetch (POST + body, which EventSource can't do).
 * Adds the bearer token from local storage and triggers a global
 * unauthorized event if the server replies 401.
 */
import { authHeaders, triggerUnauthorized } from "./auth";

export type SSEEvent = { event: string; data: string };

export async function postSSE(
  url: string,
  init: RequestInit,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers = { ...(init.headers || {}), ...authHeaders() };
  const r = await fetch(url, { ...init, headers, signal });
  if (r.status === 401 || r.status === 403) {
    triggerUnauthorized();
    throw new Error("unauthorized");
  }
  if (!r.ok || !r.body) throw new Error(`SSE failed: ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      onEvent({ event, data: dataLines.join("\n") });
    }
  }
}
