import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { api } from "../lib/api";
import { setToken, isLoggedIn } from "../lib/auth";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const redirectTo = (loc.state as any)?.from || "/";

  useEffect(() => {
    if (isLoggedIn()) nav(redirectTo, { replace: true });
    // Tell us whether the backend has auth turned on. If not, auto-log-in.
    api<any>("/api/auth/status")
      .then((r) => {
        setAuthRequired(!!r.auth_required);
        if (!r.auth_required) doLogin("");
      })
      .catch(() => setAuthRequired(true));
  }, []);

  const doLogin = async (pw: string) => {
    setError(null); setBusy(true);
    try {
      const res = await api<any>("/api/auth/login", {
        method: "POST", body: JSON.stringify({ password: pw }),
      });
      setToken(res.token);
      nav(redirectTo, { replace: true });
    } catch (e: any) {
      const msg = String(e?.message || "");
      setError(msg.includes("401") ? "Incorrect password." : msg || "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); doLogin(password); };

  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 mb-7">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-accent to-accent-deep grid place-items-center shadow-glow">
            <svg viewBox="0 0 32 32" className="h-5 w-5">
              <path d="M5 16 L10 16 L12 10 L16 22 L18 16 L27 16" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <div className="font-display text-[20px] font-semibold text-ink-50 leading-none">Folio</div>
            <div className="text-[10.5px] uppercase tracking-[0.2em] text-ink-300 mt-1">Your medical record</div>
          </div>
        </div>

        <div className="card card-pad">
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-ink-50">Sign in</h1>
          <p className="text-[13px] text-ink-300 mt-1.5 leading-relaxed">
            Folio is single-user. Enter the password configured on the server.
          </p>

          {authRequired === false ? (
            <div className="mt-4 rounded-lg border border-good/30 bg-good-softer px-3 py-2.5 text-[12.5px] text-good-ink">
              Auth is disabled on this server. Logging you in…
            </div>
          ) : (
            <form onSubmit={onSubmit} className="mt-5 space-y-3">
              <label className="block">
                <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold mb-1">Password</div>
                <input
                  type="password" autoFocus
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="input" placeholder="••••••••" disabled={busy}
                />
              </label>
              {error && (
                <div className="rounded-lg border border-alert/30 bg-alert-softer px-3 py-2 text-[12.5px] text-alert-ink">
                  {error}
                </div>
              )}
              <button type="submit" disabled={busy || !password}
                      className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}
        </div>

        <p className="text-[11px] text-ink-300 mt-4 text-center leading-relaxed">
          Not medical advice. Decisions about your care belong with a licensed clinician.
        </p>
      </div>
    </div>
  );
}
