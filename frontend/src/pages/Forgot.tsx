import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { friendlyError } from "../lib/errors";
import { Brand, Disclaimer, Field } from "./Login";

/**
 * Forgot-password page.
 *
 * Posts the username to /api/auth/forgot — the backend always returns 200
 * (whether or not the username exists) so this endpoint can't be used to
 * enumerate accounts. If the user has an email on file, a reset link is
 * mailed to them. If they don't, the link is logged on the server.
 */
export default function ForgotPage() {
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      await api("/api/auth/forgot", {
        method: "POST",
        body: JSON.stringify({ username: username.trim().toLowerCase() }),
      });
      setSubmitted(true);
    } catch (e: any) {
      setError(friendlyError(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid place-items-center px-6">
      <div className="w-full max-w-sm">
        <Brand />
        <div className="card card-pad mt-6">
          <h1 className="font-display text-[20px] font-semibold tracking-tight text-ink-50">Reset your password</h1>
          {!submitted ? (
            <>
              <p className="text-[13px] text-ink-200 mt-2 leading-relaxed">
                Enter your username. If we have an email on file, we'll send you a link to set a new password.
              </p>
              <form onSubmit={submit} className="mt-4 space-y-3">
                <Field label="Username">
                  <input
                    type="text" autoFocus autoCapitalize="off" autoCorrect="off"
                    value={username} onChange={(e) => setUsername(e.target.value)}
                    className="input" placeholder="rishika" disabled={busy}
                  />
                </Field>
                {error && (
                  <div className="rounded-lg border border-alert/30 bg-alert-softer px-3 py-2 text-[12.5px] text-alert-ink">{error}</div>
                )}
                <button type="submit" disabled={busy || !username.trim()}
                        className="btn btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed">
                  {busy ? "Sending…" : "Send reset link"}
                </button>
              </form>
            </>
          ) : (
            <p className="text-[13px] text-ink-200 mt-2 leading-relaxed">
              If a Folio account exists for that username with an email on file, a reset link is on its way.
              The link expires in 30 minutes. Check your spam folder if you don't see it.
            </p>
          )}
          <div className="text-[12.5px] text-ink-300 mt-4">
            <Link to="/login" className="link">← Back to sign in</Link>
          </div>
        </div>
        <Disclaimer />
      </div>
    </div>
  );
}
