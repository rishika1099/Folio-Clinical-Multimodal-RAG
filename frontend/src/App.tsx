import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { AuthGuard } from "./components/AuthGuard";
import ChatPage from "./pages/Chat";
import Overview from "./pages/Overview";
import TimelinePage from "./pages/Timeline";
import IngestPage from "./pages/Ingest";
import SuggestionsPage from "./pages/Suggestions";
import ReportDetailPage from "./pages/ReportDetail";
import DevPage from "./pages/Dev";
import LoginPage from "./pages/Login";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="*" element={
        <AuthGuard>
          <Shell>
            <Routes>
              <Route path="/" element={<ChatPage />} />
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
