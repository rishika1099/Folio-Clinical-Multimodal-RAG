import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { isLoggedIn } from "../lib/auth";

/**
 * Wraps all in-app routes. Redirects to /login if no token is present
 * AND listens for the global "folio:unauthorized" event so a 401 from
 * any API call kicks the user out cleanly.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const [authed, setAuthed] = useState(isLoggedIn());

  useEffect(() => {
    const onChange = () => setAuthed(isLoggedIn());
    window.addEventListener("folio:auth-changed", onChange);
    window.addEventListener("folio:unauthorized", onChange);
    return () => {
      window.removeEventListener("folio:auth-changed", onChange);
      window.removeEventListener("folio:unauthorized", onChange);
    };
  }, []);

  if (!authed) {
    return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  }
  return <>{children}</>;
}
