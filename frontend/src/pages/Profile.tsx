import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api, API_BASE } from "../lib/api";
import { authHeaders, clearAuth, displayName, getUser } from "../lib/auth";
import { friendlyError } from "../lib/errors";

/**
 * Profile / Settings page.
 *
 * Surfaces account-level controls that don't belong in any other tab:
 *   - Download a JSON bundle of all your Folio data
 *   - Permanently delete your account and all your data
 *   - View recent audit log entries (who-did-what on your record)
 *
 * Wired to /api/me/* endpoints which are user-scoped and audit-logged.
 */
export default function ProfilePage() {
  const user = getUser();
  const nav = useNavigate();

  const audit = useQuery<{ events: AuditEvent[] }>({
    queryKey: ["audit"],
    queryFn: () => api("/api/me/audit?limit=50"),
  });

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <header>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Settings</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Your account</h1>
        <p className="text-sm text-ink-200 mt-1.5">
          {user ? <>Signed in as <span className="font-semibold text-ink-100">{displayName(user)}</span>{" "}
            <span className="text-ink-300 font-mono">@{user.username}</span></> : "Not signed in"}
        </p>
      </header>

      <ExportCard />
      <AuditCard data={audit.data?.events || []} loading={audit.isLoading} />
      <DangerCard onDeleted={() => { clearAuth(); nav("/", { replace: true }); }} />
    </div>
  );
}

// ─── Download my data ────────────────────────────────────────────────────
function ExportCard() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const download = async () => {
    setError(null); setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/api/me/export`, { headers: authHeaders() });
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // Try to read the server-suggested filename; fall back to a sensible default.
      const disp = r.headers.get("Content-Disposition") || "";
      const match = /filename="([^"]+)"/i.exec(disp);
      a.download = match?.[1] || "folio-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(friendlyError(e));
    } finally { setBusy(false); }
  };
  return (
    <section className="card card-pad">
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Your data</div>
      <h2 className="font-display text-[18px] font-semibold tracking-tight text-ink-50 mt-1">Download everything</h2>
      <p className="text-[13.5px] text-ink-200 mt-2 leading-relaxed">
        A single JSON file with every report, diagnosis, medication, vital, lab, and embedding Folio has saved for you.
        Good for keeping your own backup, or for switching to a different tool — it's your record.
      </p>
      <div className="mt-4 flex items-center gap-2">
        <button onClick={download} disabled={busy} className="btn btn-primary text-[13px] py-2 px-4">
          {busy ? "Preparing…" : "Download JSON"}
        </button>
        {error && <span className="text-[12.5px] text-alert-deep">{error}</span>}
      </div>
    </section>
  );
}

// ─── Recent audit events ─────────────────────────────────────────────────
type AuditEvent = { action: string; target: string; ts: string; meta?: any };
function AuditCard({ data, loading }: { data: AuditEvent[]; loading: boolean }) {
  return (
    <section className="card card-pad">
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Activity</div>
      <h2 className="font-display text-[18px] font-semibold tracking-tight text-ink-50 mt-1">Recent activity on your account</h2>
      <p className="text-[13.5px] text-ink-200 mt-2 leading-relaxed">
        Folio logs sensitive actions on your record so you can see when reports were viewed, when you chatted, and
        when you exported your data. Logs older than 180 days are removed automatically.
      </p>
      <div className="mt-4 rounded-lg border border-ink-700 overflow-hidden">
        {loading ? (
          <div className="p-4 text-[12.5px] text-ink-300">Loading…</div>
        ) : data.length === 0 ? (
          <div className="p-4 text-[12.5px] text-ink-300">No activity yet.</div>
        ) : (
          <ul className="divide-y divide-ink-700">
            {data.map((e, i) => (
              <li key={i} className="px-3 py-2 text-[12.5px] flex items-center justify-between gap-3">
                <span className="font-mono text-ink-100">{labelOf(e.action)}</span>
                <span className="text-ink-300 font-mono truncate">{e.target}</span>
                <span className="text-ink-300 font-mono num shrink-0">{relative(e.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function labelOf(action: string): string {
  return ({
    "chat_query":      "chat asked",
    "view_report":     "opened report",
    "export":          "downloaded data",
    "delete_account":  "deleted account",
    "consensus_run":   "high-confidence extract",
  } as Record<string, string>)[action] || action;
}

function relative(iso: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const dt = (Date.now() - t) / 1000;
  if (dt < 60) return "just now";
  if (dt < 3600) return `${Math.floor(dt/60)}m ago`;
  if (dt < 86400) return `${Math.floor(dt/3600)}h ago`;
  return `${Math.floor(dt/86400)}d ago`;
}

// ─── Delete account ──────────────────────────────────────────────────────
function DangerCard({ onDeleted }: { onDeleted: () => void }) {
  const user = getUser();
  const [confirming, setConfirming] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const proceed = async () => {
    setError(null); setBusy(true);
    try {
      await api("/api/me", {
        method: "DELETE",
        body: JSON.stringify({ confirm: text.trim().toLowerCase() }),
      });
      onDeleted();
    } catch (e: any) {
      setError(friendlyError(e));
    } finally { setBusy(false); }
  };

  return (
    <section className="card card-pad border border-alert/30">
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-alert-deep font-semibold">Danger zone</div>
      <h2 className="font-display text-[18px] font-semibold tracking-tight text-ink-50 mt-1">Delete my account</h2>
      <p className="text-[13.5px] text-ink-200 mt-2 leading-relaxed">
        Permanently removes your account, every report you've uploaded, all extracted data, your embeddings, and your
        original PDF/image attachments. This <span className="font-semibold">cannot be undone</span>. Download your data
        first if you might want it back.
      </p>
      {!confirming ? (
        <button onClick={() => setConfirming(true)} className="mt-4 btn btn-ghost text-[13px] py-2 px-4 border border-alert/40 text-alert-deep hover:bg-alert-softer">
          Delete my account…
        </button>
      ) : (
        <div className="mt-4 rounded-lg border border-alert/30 bg-alert-softer p-3">
          <div className="text-[13px] text-alert-ink leading-relaxed">
            Type your username <span className="font-mono font-semibold">{user?.username}</span> to confirm.
          </div>
          <input
            type="text" autoFocus value={text} onChange={(e) => setText(e.target.value)}
            placeholder={user?.username || ""}
            className="mt-2 w-full rounded-lg border border-alert/40 bg-white px-3 py-2 text-[14px] font-mono focus:outline-none focus:border-alert"
          />
          <div className="mt-3 flex items-center gap-2">
            <button onClick={proceed} disabled={busy || text.trim().toLowerCase() !== (user?.username || "").toLowerCase()}
                    className="btn text-[13px] py-2 px-4 bg-alert text-white hover:bg-alert-deep disabled:opacity-50">
              {busy ? "Deleting…" : "Yes, delete everything"}
            </button>
            <button onClick={() => { setConfirming(false); setText(""); setError(null); }}
                    className="btn btn-ghost text-[13px] py-2 px-4">Cancel</button>
            {error && <span className="text-[12.5px] text-alert-deep">{error}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
