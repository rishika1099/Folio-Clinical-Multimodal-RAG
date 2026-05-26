import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { isLoggedIn, setAuth } from "../lib/auth";
import { Brand, Disclaimer, Field } from "./Login";

export default function SignupPage() {
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allowSignup, setAllowSignup] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    if (isLoggedIn()) nav("/", { replace: true });
    api<any>("/api/auth/status").then(r => setAllowSignup(!!r.allow_signup)).catch(() => {});
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    if (password.length < 6)   { setError("Password must be at least 6 characters."); return; }
    setError(null); setBusy(true);
    try {
      const res = await api<any>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: username.trim().toLowerCase(),
          password,
          display_name: displayName.trim(),
        }),
      });
      setAuth(res.token, res.user);
      nav("/", { replace: true });
    } catch (e: any) {
      const msg = String(e?.message || "");
      if (msg.includes("409")) setError("That username is already taken.");
      else if (msg.includes("400")) setError("Username or password didn't meet the requirements.");
      else if (msg.includes("403")) setError("Signups are disabled on this server.");
      else setError(msg || "Sign-up failed.");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center px-6 py-10">
      <div className="w-full max-w-sm">
        <Brand />
        <div className="card card-pad">
          <h1 className="font-display text-[22px] font-semibold tracking-tight text-ink-50">Create your account</h1>
          <p className="text-[13px] text-ink-300 mt-1.5 leading-relaxed">
            Your record is yours. Other Folio users can't see anything you upload.
          </p>

          {!allowSignup ? (
            <div className="mt-5 rounded-lg border border-warn/30 bg-warn-softer px-3 py-2.5 text-[12.5px] text-warn-ink">
              Sign-ups are disabled on this instance. <Link to="/login" className="link">Sign in</Link> with an existing account.
            </div>
          ) : (
            <form onSubmit={submit} className="mt-5 space-y-3">
              <Field label="Username">
                <input
                  type="text" autoFocus autoCapitalize="off" autoCorrect="off"
                  value={username} onChange={(e) => setUsername(e.target.value)}
                  className="input" placeholder="rishika" disabled={busy}
                />
              </Field>
              <Field label="Display name (optional)">
                <input
                  type="text"
                  value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                  className="input" placeholder="Rishika M." disabled={busy}
                />
              </Field>
              <Field label="Password">
                <input
                  type="password" minLength={6}
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="input" placeholder="at least 6 characters" disabled={busy}
                />
              </Field>
              <Field label="Confirm password">
                <input
                  type="password"
                  value={confirm} onChange={(e) => setConfirm(e.target.value)}
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
                {busy ? "Creating…" : "Create account"}
              </button>
            </form>
          )}

          <div className="text-[12.5px] text-ink-300 mt-4 text-center">
            Already have an account? <Link to="/login" className="link">Sign in</Link>
          </div>
        </div>
        <Disclaimer />
      </div>
    </div>
  );
}
