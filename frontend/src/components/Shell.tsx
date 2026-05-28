import { NavLink, Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import clsx from "clsx";
import { clearAuth, displayName, getUser } from "../lib/auth";

/** Engineer-only routes (eval dashboard, internal model panel) are hidden
 *  by default so non-technical users don't see them.
 *  Reveal them by appending `?eng=1` to any URL once (persisted in
 *  localStorage). Append `?eng=0` to disable again. */
const ENG_KEY = "folio:engineer-mode";
function readEngineerMode(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const params = new URLSearchParams(window.location.search);
    const flag = params.get("eng");
    if (flag === "1") { localStorage.setItem(ENG_KEY, "1"); return true; }
    if (flag === "0") { localStorage.removeItem(ENG_KEY); return false; }
    return localStorage.getItem(ENG_KEY) === "1";
  } catch { return false; }
}

const NAV = [
  { to: "/",            label: "Chat",        icon: <IconChat />,  eng: false },
  { to: "/overview",    label: "Overview",    icon: <IconHome />,  eng: false },
  { to: "/timeline",    label: "Timeline",    icon: <IconTime />,  eng: false },
  { to: "/suggestions", label: "Insights",    icon: <IconSpark />, eng: false },
  { to: "/profile",     label: "Account",     icon: <IconUser />,  eng: false },
  { to: "/dev",         label: "Engine",      icon: <IconCode />,  eng: true  },
  { to: "/benchmarks",  label: "Benchmarks",  icon: <IconChart />, eng: true  },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const [engineer, setEngineer] = useState(readEngineerMode);
  useEffect(() => { setEngineer(readEngineerMode()); }, []);
  const visibleNav = engineer ? NAV : NAV.filter(n => !n.eng);

  // Mobile drawer state. The sidebar is hidden by default on screens
  // narrower than `md` (768px) and slides in when `drawer` is true.
  const [drawer, setDrawer] = useState(false);
  // Close the drawer on route change so navigating from the sidebar lands
  // on the new page without a stale overlay.
  const close = () => setDrawer(false);

  return (
    <div className="min-h-full md:grid md:grid-cols-[260px_1fr]">
      {/* Backdrop (mobile only, shown when drawer is open) */}
      {drawer && (
        <button aria-label="Close menu" onClick={close}
                className="md:hidden fixed inset-0 z-30 bg-ink-900/40 backdrop-blur-sm"/>
      )}

      <aside className={clsx(
        // Mobile: off-canvas drawer
        "md:sticky md:top-0 md:translate-x-0 md:h-screen",
        "fixed inset-y-0 left-0 z-40 w-[280px] max-w-[85vw] transition-transform duration-200",
        drawer ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        "border-r border-ink-700 bg-white/95 md:bg-white/60 backdrop-blur-xl px-4 py-6 flex flex-col",
      )}>
        <div className="flex items-center justify-between mb-7">
          <Link to="/" onClick={close} className="flex items-center gap-2.5 px-1">
            <Logo />
            <div className="leading-tight">
              <div className="font-display text-[19px] font-semibold tracking-tight text-ink-50">Folio</div>
              <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300">Your medical record</div>
            </div>
          </Link>
          {/* Close button — mobile only */}
          <button aria-label="Close menu" onClick={close}
                  className="md:hidden p-1 -mr-1 text-ink-300 hover:text-ink-100">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="px-2 mb-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Workspace</div>
        </div>
        <nav className="flex flex-col gap-1">
          {visibleNav.map(n => (
            <NavLink
              key={n.to} to={n.to} end={n.to === "/"}
              onClick={close}
              className={({ isActive }) => clsx("navlink", isActive && "is-active")}
            >
              <span className="text-ink-300 w-4 grid place-items-center">{n.icon}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto space-y-2">
          <SignOut />
          <Disclaimer />
        </div>
      </aside>

      <main className="min-w-0 flex flex-col">
        <Topbar onMenu={() => setDrawer(true)} />
        <div className="px-4 sm:px-6 md:px-8 py-5 md:py-7 max-w-[1400px] flex-1 w-full">
          {children}
        </div>
        <Footer />
      </main>
    </div>
  );
}

function Logo() {
  return (
    <div className="relative h-9 w-9 rounded-xl bg-gradient-to-br from-accent to-accent-deep flex items-center justify-center shadow-glow">
      <svg viewBox="0 0 32 32" className="h-5 w-5">
        <path d="M5 16 L10 16 L12 10 L16 22 L18 16 L27 16" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  return (
    <div className="sticky top-0 z-10 border-b border-ink-700 bg-ink-950/85 backdrop-blur-xl">
      <div className="flex items-center justify-between px-4 md:px-8 h-14 gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* Hamburger — mobile only */}
          <button aria-label="Open menu" onClick={onMenu}
                  className="md:hidden p-1.5 -ml-1.5 text-ink-200 hover:text-ink-50 rounded-lg hover:bg-ink-800/50">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round"/>
            </svg>
          </button>
          <Crumbs />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-ink-300 hidden sm:inline">{today}</span>
        </div>
      </div>
    </div>
  );
}

function Crumbs() {
  const u = getUser();
  return (
    <div className="flex items-center gap-2 text-[13px]">
      <span className="text-ink-300">workspace</span>
      <span className="text-ink-400">/</span>
      <span className="text-ink-100 font-medium">{u?.username || "—"}</span>
    </div>
  );
}

function SignOut() {
  const nav = useNavigate();
  const u = getUser();
  const onClick = () => { clearAuth(); nav("/login", { replace: true }); };
  return (
    <button onClick={onClick}
            className="w-full flex items-center justify-between gap-2 rounded-xl border border-ink-700 bg-white px-3 py-2 text-[12px] text-ink-200 hover:bg-ink-850 hover:text-ink-100 transition">
      <span className="flex items-center gap-2">
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M15 17l5-5-5-5M20 12H9M12 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        Sign out
      </span>
      <span className="text-[10px] text-ink-300 font-mono truncate max-w-[80px]">{u?.username || "—"}</span>
    </button>
  );
}

function Disclaimer() {
  return (
    <div className="rounded-xl border border-warn/30 bg-warn-softer px-3 py-2.5 text-[11px] leading-snug text-warn-ink">
      <div className="font-medium text-warn-deep mb-0.5">Not medical advice</div>
      Folio surfaces patterns. Decisions about your care belong with a licensed clinician.
    </div>
  );
}

function Footer() {
  return (
    <footer className="px-4 sm:px-6 md:px-8 py-5 mt-6 border-t border-ink-700 text-[11.5px] text-ink-300 flex flex-wrap items-center justify-between gap-3"
            style={{ paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}>
      <div>Built by <span className="text-ink-100 font-medium">Rishika Mamidibathula</span></div>
      <div className="text-ink-400">© 2026 · All rights reserved</div>
    </footer>
  );
}

/* ---------- icons ---------- */
const sIcon = "h-4 w-4";
function IconHome() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" strokeLinejoin="round"/></svg>; }
function IconPlus() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 5v14M5 12h14" strokeLinecap="round"/></svg>; }
function IconTime() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2" strokeLinecap="round"/></svg>; }
function IconSpark() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.8 2.8M15.2 15.2 18 18M6 18l2.8-2.8M15.2 8.8 18 6"/></svg>; }
function IconCode() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m9 8-4 4 4 4M15 8l4 4-4 4" strokeLinecap="round" strokeLinejoin="round"/></svg>; }
function IconChat() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4 3.5v-3.5h-.5A1.5 1.5 0 0 1 4 15.5z" strokeLinejoin="round"/></svg>; }
function IconChart() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" strokeLinecap="round"/></svg>; }
function IconUser() { return <svg className={sIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" strokeLinecap="round"/></svg>; }
