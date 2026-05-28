import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { friendlyError } from "../lib/errors";
import { Brand, Disclaimer, Field } from "./Login";

/**
 * Reset-password page. Reached from the email link as /reset?token=…
 * The token is verified server-side; on success the user is bounced to
 * the login page with a banner.
 */
export default function ResetPage() {
  const [search] = useSearchParams();
  const nav = useNavigate();
  const token = search.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) setError("This reset link is missing a token. Request a new one.");
  }, [token]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters."); return; }
    setError(null); setBusy(true);
    try {
      await api("/api/auth/reset", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      nav("/login?reset=ok", { replace: true });
    } catch (e: any) {
      setError(friendlyError(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="w-full max-w-sm">
        <Brand />
        <div className="card card-pad mt-6">
          <h1 className="font-display text-[20px] font-semibold tracking-tight text-ink-50">Set a new password</h1>
          <p className="text-[13px] text-ink-200 mt-2 leading-relaxed">
            Pick something at least 6 characters long. You'll be signed back in once it's set.
          </p>
          <form onSubmit={submit} className="mt-4 space-y-3">
            <Field label="New password">
              <input
                type="password" autoFocus
                value={password} onChange={(e) => setPassword(e.target.value)}
                className="input" placeholder="••••••••" disabled={busy}
              />
            </Field>
            <Field label="Confirm new password">
              <input
                type="password"
                value={confirm} onChange={(e) => setConfirm(e.target.value)}
                className="input" placeholder="••••••••" disabled={busy}
              />
            </Field>
            {error && (
              <div className="rounded-lg border border-alert/30 bg-alert-softer px-3 py-2 text-[12.5px] text-alert-ink">{error}</div>
            )}
            <button type="submit" disabled={busy || !token}
                    className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
              {busy ? "Saving…" : "Save new password"}
            </button>
          </form>
          <div className="text-[12.5px] text-ink-300 mt-4">
            <Link to="/login" className="link">← Back to sign in</Link>
          </div>
        </div>
        <Disclaimer />
      </div>
    </div>
  );
}
