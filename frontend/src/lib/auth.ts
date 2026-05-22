/**
 * Tiny auth store. Holds the bearer JWT in localStorage; gives a
 * subscribe hook so any component can react to login/logout events.
 *
 * Listens for a "folio:unauthorized" custom event so the api wrapper can
 * trigger a global redirect to /login when it sees a 401.
 */
const KEY = "folio.token";

export function getToken(): string | null {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function setToken(t: string): void {
  try { localStorage.setItem(KEY, t); } catch {}
  window.dispatchEvent(new Event("folio:auth-changed"));
}

export function clearToken(): void {
  try { localStorage.removeItem(KEY); } catch {}
  window.dispatchEvent(new Event("folio:auth-changed"));
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export function triggerUnauthorized(): void {
  clearToken();
  window.dispatchEvent(new Event("folio:unauthorized"));
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}
