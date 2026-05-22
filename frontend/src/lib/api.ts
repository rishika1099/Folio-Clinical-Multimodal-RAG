import { authHeaders, triggerUnauthorized } from "./auth";

const BASE = (import.meta as any).env?.VITE_API_URL || "";

async function checkAuth(r: Response) {
  if (r.status === 401 || r.status === 403) {
    triggerUnauthorized();
    throw new Error("unauthorized");
  }
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(init?.headers || {}) },
    ...init,
  });
  await checkAuth(r);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export async function apiForm<T = any>(path: string, form: FormData): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST", body: form,
    headers: { ...authHeaders() },
  });
  await checkAuth(r);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const API_BASE = BASE;
