/**
 * Multi-user auth store. JWT + current user record in localStorage.
 * Components subscribe to "folio:auth-changed" to re-render on login/logout.
 */
const KEY_TOKEN = "folio.token";
const KEY_USER  = "folio.user";

export type CurrentUser = {
  user_id: string;
  username: string;
  display_name?: string;
};

export function getToken(): string | null {
  try { return localStorage.getItem(KEY_TOKEN); } catch { return null; }
}

export function getUser(): CurrentUser | null {
  try {
    const raw = localStorage.getItem(KEY_USER);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function setAuth(token: string, user: CurrentUser): void {
  try {
    localStorage.setItem(KEY_TOKEN, token);
    localStorage.setItem(KEY_USER, JSON.stringify(user));
  } catch {}
  window.dispatchEvent(new Event("folio:auth-changed"));
}

export function clearAuth(): void {
  try {
    localStorage.removeItem(KEY_TOKEN);
    localStorage.removeItem(KEY_USER);
  } catch {}
  window.dispatchEvent(new Event("folio:auth-changed"));
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export function triggerUnauthorized(): void {
  clearAuth();
  window.dispatchEvent(new Event("folio:unauthorized"));
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function displayName(): string {
  const u = getUser();
  if (!u) return "there";
  return (u.display_name || u.username || "there").trim();
}

export function initials(): string {
  const u = getUser();
  if (!u) return "?";
  const src = u.display_name || u.username || "";
  const parts = src.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 1).toUpperCase() || "?";
}
