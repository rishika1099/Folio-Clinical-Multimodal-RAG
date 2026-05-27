import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1">
        <Hero />
        <Capabilities />
        <HowItWorks />
        <Privacy />
        <CTA />
      </main>
      <Footer />
    </div>
  );
}

// ─── header ────────────────────────────────────────────────────────────────
function Header() {
  return (
    <header className="border-b border-ink-700 bg-ink-950/80 backdrop-blur-xl sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <Logo />
          <div className="leading-tight">
            <div className="font-display text-[18px] font-semibold text-ink-50">Folio</div>
            <div className="text-[9.5px] uppercase tracking-[0.22em] text-ink-300 mt-0.5">Your medical record</div>
          </div>
        </Link>
        <nav className="flex items-center gap-1.5 sm:gap-3">
          <Link to="/login" className="text-[13px] text-ink-200 hover:text-ink-50 px-3 py-2 transition">
            Sign in
          </Link>
          <Link to="/signup" className="btn btn-primary text-[13px] py-1.5 px-3.5">
            Get started
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Logo() {
  return (
    <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-accent to-accent-deep grid place-items-center shadow-glow">
      <svg viewBox="0 0 32 32" className="h-5 w-5">
        <path d="M5 16 L10 16 L12 10 L16 22 L18 16 L27 16"
              fill="none" stroke="white" strokeWidth="2.5"
              strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

// ─── hero ──────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-6 pt-16 sm:pt-24 pb-12 sm:pb-20">
      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-10 lg:gap-16 items-center">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-accent-deep font-semibold">
            Your health, organised
          </div>
          <h1 className="font-display text-[40px] sm:text-[52px] leading-[1.05] font-semibold tracking-tight text-ink-50 mt-3">
            Every PDF, photo, and note about your health
            <span className="text-accent-deep"> — finally in one place.</span>
          </h1>
          <p className="text-[16px] sm:text-[17px] text-ink-200 mt-5 leading-relaxed max-w-xl">
            Folio is a personal medical record companion. Drop in a lab PDF, snap a photo of a paper report or skin condition, dictate symptoms, paste a clinic note. Folio extracts the structure, builds your longitudinal timeline, and answers questions about your own record in chat.
          </p>
          <p className="text-[12.5px] text-ink-300 mt-5">
            Free · each user&apos;s record is fully private · not medical advice.
          </p>
        </div>
        <HeroVisual />
      </div>
    </section>
  );
}

/**
 * Hero visual = scripted chat playing out on a loop.
 *
 *   step 1  user message rises
 *   step 2  typing dots rise (replaces nothing — appears below user msg)
 *   step 3  typing collapses; Folio reply with citations rises in its place
 *   step 4  lab-ingest card rises
 *   step 5  hold for a beat
 *   loop    fade everything out and restart
 */
function HeroVisual() {
  const [step, setStep] = useState(0);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    const timers: number[] = [];
    const run = () => {
      setStep(0);
      timers.push(window.setTimeout(() => setStep(1), 200));   // user
      timers.push(window.setTimeout(() => setStep(2), 1100));  // typing
      timers.push(window.setTimeout(() => setStep(3), 2700));  // reply
      timers.push(window.setTimeout(() => setStep(4), 4400));  // ingest
      timers.push(window.setTimeout(() => {                    // restart
        setCycle(c => c + 1);
        run();
      }, 9500));
    };
    run();
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="relative h-[400px] lg:h-[440px]">
      <div className="absolute -top-10 -right-6 w-72 h-72 rounded-full bg-accent-soft/55 blur-3xl pointer-events-none" />
      <div className="absolute -bottom-4 left-4 w-64 h-64 rounded-full bg-warn-soft/45 blur-3xl pointer-events-none" />

      <div className="relative h-full flex flex-col gap-3 items-end justify-center">
        {step >= 1 && (
          <Bubble key={`user-${cycle}`} tone="accent" eyebrow="You · just now">
            Is my BP trending up?
          </Bubble>
        )}

        {step === 2 && (
          <Bubble key={`typing-${cycle}`} tone="white" eyebrow="Folio is thinking">
            <Dots />
          </Bubble>
        )}

        {step >= 3 && (
          <Bubble key={`reply-${cycle}`} tone="white" eyebrow="Folio · cited 3 reports">
            Yes — your systolic has climbed{" "}
            <span className="font-mono num">124 → 132 → 144</span>{" "}
            over your last three readings.
          </Bubble>
        )}

        {step >= 4 && (
          <Bubble key={`ingest-${cycle}`} tone="info" eyebrow="Lab PDF · ingested" mono>
            HbA1c 7.2% · LDL 142 · Creatinine 1.0
          </Bubble>
        )}
      </div>
    </div>
  );
}

function Bubble({ tone, eyebrow, children, mono }: {
  tone: "accent" | "white" | "info";
  eyebrow: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  const toneCls = tone === "accent"
    ? "bg-accent text-white shadow-glow"
    : tone === "info"
      ? "bg-info-soft text-info-ink border border-info/25"
      : "bg-white text-ink-100 border border-ink-700 shadow-card";
  const eyebrowCls = tone === "accent" ? "text-white/70"
                    : tone === "info"   ? "text-info-deep/75"
                                        : "text-ink-300";
  return (
    <div className={`max-w-[82%] rounded-2xl px-4 py-3 animate-rise ${toneCls}`}>
      <div className={`text-[10px] uppercase tracking-[0.14em] font-semibold ${eyebrowCls}`}>
        {eyebrow}
      </div>
      <div className={`text-[14px] leading-snug mt-1 ${mono ? "font-mono num" : ""}`}>
        {children}
      </div>
    </div>
  );
}

function Dots() {
  return (
    <span className="inline-flex gap-1.5 items-center py-1">
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{ animationDelay: "0ms" }}/>
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{ animationDelay: "200ms" }}/>
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{ animationDelay: "400ms" }}/>
    </span>
  );
}

// ─── capabilities ──────────────────────────────────────────────────────────
function Capabilities() {
  const items = [
    {
      title: "Multimodal ingest",
      body: "PDF labs, photos of paper reports, photos of body parts, voice memos, raw text. Everything converges on one structured schema — diagnoses, medications, vitals, labs, symptoms, red flags.",
      icon: <IconLayers />,
      tone: "accent" as const,
    },
    {
      title: "Chat grounded in your record",
      body: '"When was my last A1C?" gets the actual number with the date and a citation back to the report. Folio retrieves the relevant passages from your own history — it can\'t fabricate numbers it doesn\'t have.',
      icon: <IconChat />,
      tone: "info" as const,
    },
    {
      title: "Clinical-vision on photos",
      body: "Snap a skin condition or eye. Folio describes the visible findings in plain language, lists possible considerations with hedged language, and flags anything concerning that warrants urgent care.",
      icon: <IconCamera />,
      tone: "warn" as const,
    },
    {
      title: "Multi-LLM consensus",
      body: "For high-stakes documents, flip to High-conf mode. Folio runs Claude, GPT, and Gemini in parallel, aligns their outputs with embedding similarity, and shows per-field agreement so you know what to trust.",
      icon: <IconStack />,
      tone: "good" as const,
    },
    {
      title: "Longitudinal timeline",
      body: "Every ingest feeds the same timeline. Blood pressure, A1C, LDL, weight, lab flags — all charted across months and years, with the source report one click away.",
      icon: <IconTrend />,
      tone: "info" as const,
    },
    {
      title: "Six suggestion lenses",
      body: "After every report, Folio looks at trends, drug interactions (against a curated database, never the LLM), follow-up reminders, differentials, lifestyle, and risk indicators — flagging what needs attention.",
      icon: <IconSpark />,
      tone: "accent" as const,
    },
  ];
  return (
    <section className="max-w-6xl mx-auto px-6 py-12 sm:py-16">
      <div className="max-w-2xl mb-10">
        <div className="text-[10.5px] uppercase tracking-[0.22em] text-accent-deep font-semibold">
          What Folio does
        </div>
        <h2 className="font-display text-[30px] sm:text-[36px] font-semibold tracking-tight text-ink-50 mt-2">
          Built for the way personal health data actually lives.
        </h2>
        <p className="text-[15px] text-ink-200 mt-3 leading-relaxed">
          Scattered across PDFs in your downloads, photos in your camera roll, and notes in your phone.
          Folio takes that mess seriously: one schema, one timeline, one place to ask.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {items.map(i => <CapCard key={i.title} {...i} />)}
      </div>
    </section>
  );
}

function CapCard({ title, body, icon, tone }: {
  title: string; body: string; icon: React.ReactNode;
  tone: "accent" | "info" | "warn" | "good";
}) {
  const tints = {
    accent: "bg-accent-soft text-accent-deep",
    info:   "bg-info-soft text-info-deep",
    warn:   "bg-warn-soft text-warn-deep",
    good:   "bg-good-soft text-good-deep",
  }[tone];
  return (
    <div className="card card-pad">
      <div className={`h-10 w-10 rounded-xl ${tints} grid place-items-center mb-3.5`}>
        {icon}
      </div>
      <h3 className="font-display text-[16.5px] font-semibold tracking-tight text-ink-50">{title}</h3>
      <p className="text-[13.5px] text-ink-200 mt-1.5 leading-relaxed">{body}</p>
    </div>
  );
}

// ─── how it works ──────────────────────────────────────────────────────────
function HowItWorks() {
  const steps = [
    { n: "01", title: "Sign up",
      body: "Pick a username and password. Each account is fully partitioned at the database level — your record is yours alone." },
    { n: "02", title: "Drop your record in",
      body: "PDFs, photos, voice memos, free text — any combination, any order. Folio extracts the structure and starts building your timeline." },
    { n: "03", title: "Ask anything",
      body: "Folio cites your own reports back to you, by date. No hand-waving. No fabricated numbers." },
  ];
  return (
    <section className="bg-ink-900/50 border-y border-ink-700 py-16 sm:py-20">
      <div className="max-w-6xl mx-auto px-6">
        <div className="max-w-xl mb-10">
          <div className="text-[10.5px] uppercase tracking-[0.22em] text-accent-deep font-semibold">
            How it works
          </div>
          <h2 className="font-display text-[30px] sm:text-[36px] font-semibold tracking-tight text-ink-50 mt-2">
            Three steps. About a minute to set up.
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map(s => (
            <div key={s.n}>
              <div className="font-display text-[44px] font-semibold text-accent-deep/40 num leading-none">{s.n}</div>
              <h3 className="font-display text-[18px] font-semibold tracking-tight text-ink-50 mt-3">{s.title}</h3>
              <p className="text-[14px] text-ink-200 mt-2 leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── privacy ───────────────────────────────────────────────────────────────
function Privacy() {
  const points = [
    { title: "Per-user database partitioning",
      body: "Every Mongo query is filtered by your user_id. Your record can never surface in another user's chat retrieval, timeline, or suggestions." },
    { title: "PII scrubbing before model calls",
      body: "Identifiers (SSN, MRN, phone, email, DOB) are stripped from input text before it leaves Folio's process. Provider logs never see them." },
    { title: "JWT-authenticated API",
      body: "Every request to the backend carries a per-session bearer token. The frontend can't read another user's data even with a bug." },
  ];
  return (
    <section className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
      <div className="max-w-2xl mb-8">
        <div className="text-[10.5px] uppercase tracking-[0.22em] text-accent-deep font-semibold">
          Privacy
        </div>
        <h2 className="font-display text-[30px] sm:text-[36px] font-semibold tracking-tight text-ink-50 mt-2">
          Your record is yours. Period.
        </h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {points.map(p => (
          <div key={p.title} className="rounded-2xl border border-ink-700 bg-ink-900/50 p-5">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-6 w-6 rounded-lg bg-good-soft text-good-deep grid place-items-center">
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4">
                  <path d="m5 12 5 5L20 7" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <h3 className="font-display text-[14.5px] font-semibold text-ink-50">{p.title}</h3>
            </div>
            <p className="text-[13px] text-ink-200 leading-relaxed">{p.body}</p>
          </div>
        ))}
      </div>
      <p className="text-[12.5px] text-ink-300 mt-6 max-w-2xl leading-relaxed">
        Folio is a portfolio project, not a certified medical device. It surfaces patterns from your own data. Decisions about your care belong with a licensed clinician.
      </p>
    </section>
  );
}

// ─── CTA ───────────────────────────────────────────────────────────────────
function CTA() {
  return (
    <section className="max-w-6xl mx-auto px-6 pb-16">
      <div className="rounded-3xl bg-gradient-to-br from-accent-soft via-warn-soft/60 to-info-soft/60 p-10 sm:p-14 text-center">
        <h2 className="font-display text-[30px] sm:text-[36px] font-semibold tracking-tight text-accent-ink">
          Start with one report.
        </h2>
        <p className="text-[15px] text-ink-100 mt-3 max-w-xl mx-auto leading-relaxed">
          A photo of your last lab. A PDF discharge summary. A voice memo about a symptom. Folio takes it from there.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link to="/signup" className="btn btn-primary text-[14px] py-2.5 px-5">
            Create your account
          </Link>
          <Link to="/login" className="btn btn-ghost text-[14px] py-2.5 px-5">
            Sign in
          </Link>
        </div>
      </div>
    </section>
  );
}

// ─── footer ────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="px-8 py-6 border-t border-ink-700 text-[11.5px] text-ink-300 flex flex-wrap items-center justify-between gap-3 max-w-6xl mx-auto w-full">
      <div>Built by <span className="text-ink-100 font-medium">Rishika Mamidibathula</span></div>
      <div className="text-ink-400">© 2026 · All rights reserved</div>
    </footer>
  );
}

// ─── icons ─────────────────────────────────────────────────────────────────
function IconLayers() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 18l9 5 9-5" strokeLinejoin="round"/></svg>;
}
function IconChat() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4 3.5v-3.5h-.5A1.5 1.5 0 0 1 4 15.5z" strokeLinejoin="round"/></svg>;
}
function IconCamera() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 7h3l2-2h6l2 2h3a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" strokeLinejoin="round"/><circle cx="12" cy="13" r="4"/></svg>;
}
function IconStack() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>;
}
function IconTrend() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m4 16 4-6 4 4 8-10M14 4h6v6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}
function IconSpark() {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.8 2.8M15.2 15.2 18 18M6 18l2.8-2.8M15.2 8.8 18 6"/></svg>;
}
