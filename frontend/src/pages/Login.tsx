import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isLoggedIn, setAuth } from "../lib/auth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allowSignup, setAllowSignup] = useState(true);
  const nav = useNavigate();
  const loc = useLocation();
  const redirectTo = (loc.state as any)?.from || "/";

  useEffect(() => {
    if (isLoggedIn()) nav(redirectTo, { replace: true });
    api<any>("/api/auth/status").then(r => setAllowSignup(!!r.allow_signup)).catch(() => {});
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      const res = await api<any>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
      });
      setAuth(res.token, res.user);
      nav(redirectTo, { replace: true });
    } catch (e: any) {
      const msg = String(e?.message || "");
      setError(msg.includes("401") ? "Incorrect username or password." : msg || "Sign-in failed.");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="w-full max-w-sm">
        <Brand />
        <div className="card card-pad">
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-ink-50">Sign in</h1>
          <p className="text-[13px] text-ink-300 mt-1.5 leading-relaxed">
            Welcome back.
          </p>

          <form onSubmit={submit} className="mt-5 space-y-3">
            <Field label="Username">
              <input
                type="text" autoFocus autoCapitalize="off" autoCorrect="off"
                value={username} onChange={(e) => setUsername(e.target.value)}
                className="input" placeholder="rishika" disabled={busy}
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="input" placeholder="••••••••" disabled={busy}
              />
            </Field>
            {error && (
              <div className="rounded-lg border border-alert/30 bg-alert-softer px-3 py-2 text-[12.5px] text-alert-ink">
                {error}
              </div>
            )}
            <button type="submit" disabled={busy || !username || !password}
                    className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {allowSignup && (
            <div className="text-[12.5px] text-ink-300 mt-4 text-center">
              New here? <Link to="/signup" className="link">Create an account</Link>
            </div>
          )}
        </div>
        <Disclaimer />
      </div>
    </div>
  );
}

export function Brand() {
  return (
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
  );
}

export function Disclaimer() {
  return (
    <p className="text-[11px] text-ink-300 mt-4 text-center leading-relaxed">
      Not medical advice. Decisions about your care belong with a licensed clinician.
    </p>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold mb-1">{label}</div>
      {children}
    </label>
  );
}
