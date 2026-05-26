import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { AuthGuard } from "./components/AuthGuard";
import { isLoggedIn } from "./lib/auth";
import ChatPage from "./pages/Chat";
import Overview from "./pages/Overview";
import TimelinePage from "./pages/Timeline";
import IngestPage from "./pages/Ingest";
import SuggestionsPage from "./pages/Suggestions";
import ReportDetailPage from "./pages/ReportDetail";
import DevPage from "./pages/Dev";
import LoginPage from "./pages/Login";
import SignupPage from "./pages/Signup";
import LandingPage from "./pages/Landing";

/**
 * `/` is dual-purpose:
 *   - Unauthed visitors get the public marketing landing page.
 *   - Authed visitors get the Chat experience inside the app Shell.
 * AuthGuard handles the redirect-to-login when a session expires mid-use.
 */
function HomeRoute() {
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
  if (!authed) return <LandingPage />;
  return (
    <AuthGuard>
      <Shell><ChatPage /></Shell>
    </AuthGuard>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/"       element={<HomeRoute />} />
      <Route path="/login"  element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="*" element={
        <AuthGuard>
          <Shell>
            <Routes>
              <Route path="/overview" element={<Overview />} />
              <Route path="/ingest" element={<IngestPage />} />
              <Route path="/timeline" element={<TimelinePage />} />
              <Route path="/suggestions" element={<SuggestionsPage />} />
              <Route path="/reports/:id" element={<ReportDetailPage />} />
              <Route path="/dev" element={<DevPage />} />
            </Routes>
          </Shell>
        </AuthGuard>
      }/>
    </Routes>
  );
}
