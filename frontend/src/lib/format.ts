export function fmtDate(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch { return iso.slice(0, 10); }
}

export function fmtRelative(iso: string): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  const day = 86400_000;
  if (ms < 60_000) return "just now";
  if (ms < 3600_000) return `${Math.floor(ms/60_000)}m ago`;
  if (ms < day) return `${Math.floor(ms/3600_000)}h ago`;
  if (ms < 7*day) return `${Math.floor(ms/day)}d ago`;
  return fmtDate(iso);
}

export function clamp(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
