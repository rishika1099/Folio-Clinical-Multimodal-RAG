import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Link, useNavigate } from "react-router-dom";
import imageCompression from "browser-image-compression";

import { api, API_BASE, apiForm } from "../lib/api";
import { postSSE } from "../lib/sse";
import { fmtRelative, fmtDate } from "../lib/format";
import { displayName, initials } from "../lib/auth";

type Mode = "standard" | "consensus";

type Citation = { report_id: string; uploaded_at: string; input_type: string; score: number };

type IngestCardMsg = {
  role: "system";
  kind: "ingest";
  status: "running" | "done" | "error";
  stages?: { stage: string; ms: number }[];
  report?: any;
  consensus?: any;
  mode?: Mode;
  sourceLabel?: string;
  error?: string;
};

type ChatMsg =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; citations?: Citation[]; ragMs?: number }
  | IngestCardMsg;

const QUICK_PROMPTS = [
  { label: "I'm feeling fine",          text: "Just checking in. I feel pretty good today, no complaints." },
  { label: "I have a headache",         text: "I've had a headache today. Want to talk through it." },
  { label: "Show me my BP trend",       text: "Can you summarise how my blood pressure has been trending?" },
  { label: "What am I taking?",         text: "Remind me what medications I'm currently on and what each is for." },
  { label: "When was my last A1C?",     text: "When was my last HbA1c and what was the result?" },
  { label: "I'm anxious",               text: "I'm feeling anxious and would like to talk through it." },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("standard");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const recChunks = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const threadEnd = useRef<HTMLDivElement | null>(null);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const ctx = useQuery({ queryKey: ["chat-snapshot"], queryFn: () => api("/api/chat/snapshot") });

  useEffect(() => {
    if (messages.length || streaming) {
      threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, streaming]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["overview"] });
    qc.invalidateQueries({ queryKey: ["timeline"] });
    qc.invalidateQueries({ queryKey: ["chat-snapshot"] });
  };

  // -- chat (Standard) ------------------------------------------------------
  const sendChat = async (text: string) => {
    setError(null);
    const userMsg: ChatMsg = { role: "user", content: text };
    const placeholder: ChatMsg = { role: "assistant", content: "" };
    const next = [...messages, userMsg, placeholder];
    setMessages(next);
    setInput("");
    setStreaming(true);

    const history = next.slice(0, -1)
      .filter(m => m.role === "user" || m.role === "assistant")
      .map((m: any) => ({ role: m.role, content: m.content }));

    try {
      await postSSE(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      }, (e) => {
        if (e.event === "rag") {
          const meta = JSON.parse(e.data);
          setMessages(prev => updateLast(prev, "assistant", (m: any) =>
            ({ ...m, citations: meta.hits, ragMs: (meta.timing_ms?.embed_ms||0) + (meta.timing_ms?.search_ms||0) })));
        } else if (e.event === "delta") {
          const piece = tryParse(e.data) ?? e.data;
          setMessages(prev => updateLast(prev, "assistant", (m: any) =>
            ({ ...m, content: (m.content||"") + piece })));
        } else if (e.event === "error") {
          setError(JSON.parse(e.data).message);
          setMessages(prev => prev.slice(0, -1));
        }
      });
    } catch (err: any) {
      setError(err?.message || "stream failed");
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setStreaming(false);
    }
  };

  // -- text consensus extract (High-conf) -----------------------------------
  const extractText = async (text: string) => {
    setError(null);
    const card: IngestCardMsg = {
      role: "system", kind: "ingest", status: "running", stages: [],
      sourceLabel: text.length > 60 ? text.slice(0, 60) + "…" : text, mode: "consensus",
    };
    setMessages(prev => [...prev, card]);
    setInput("");
    setStreaming(true);
    try {
      const res = await api<any>("/api/consensus", {
        method: "POST",
        body: JSON.stringify({ text, input_type: "text" }),
      });
      setMessages(prev => updateLastIngest(prev, m => ({
        ...m, report: res.report, consensus: res.consensus, status: "done",
      })));
      invalidate();
    } catch (err: any) {
      setMessages(prev => updateLastIngest(prev, m => ({ ...m, status: "error", error: err?.message || "consensus failed" })));
    } finally {
      setStreaming(false);
    }
  };

  // -- file ingest ----------------------------------------------------------
  const handleFile = async (file: File) => {
    setError(null);
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    const isImg = file.type.startsWith("image/");
    if (!isPdf && !isImg) {
      setError("Only PDFs and images can be dropped here.");
      return;
    }
    const card: IngestCardMsg = {
      role: "system", kind: "ingest", status: "running", stages: [],
      sourceLabel: file.name, mode: "standard",
    };
    setMessages(prev => [...prev, card]);
    setStreaming(true);

    let body: File | Blob = file;
    if (isImg) { try { body = await imageCompression(file, { maxSizeMB: 1, maxWidthOrHeight: 1024 }); } catch {} }
    const fd = new FormData();
    fd.append("file", body, file.name);
    const url = `/api/ingest/${isPdf ? "pdf" : "image"}`;
    try {
      await postSSE(`${API_BASE}${url}`, { method: "POST", body: fd }, (e) => {
        if (e.event === "stage") {
          const s = JSON.parse(e.data);
          setMessages(prev => updateLastIngest(prev, m => ({ ...m, stages: [...(m.stages||[]), s] })));
        } else if (e.event === "report") {
          const report = JSON.parse(e.data);
          setMessages(prev => updateLastIngest(prev, m => ({ ...m, report, status: "done" })));
          invalidate();
        } else if (e.event === "error") {
          setMessages(prev => updateLastIngest(prev, m => ({ ...m, status: "error", error: JSON.parse(e.data).message })));
        }
      });
    } catch (err: any) {
      setMessages(prev => updateLastIngest(prev, m => ({ ...m, status: "error", error: err?.message || "ingest failed" })));
    } finally {
      setStreaming(false);
    }
  };

  // -- voice ----------------------------------------------------------------
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      recChunks.current = [];
      rec.ondataavailable = (ev) => { if (ev.data.size) recChunks.current.push(ev.data); };
      rec.onstop = async () => {
        const blob = new Blob(recChunks.current, { type: "audio/webm" });
        stream.getTracks().forEach(t => t.stop());
        setTranscribing(true);
        try {
          const fd = new FormData();
          fd.append("file", blob, "clip.webm");
          const res = await apiForm<any>("/api/chat/transcribe", fd);
          if (res?.transcript) setInput(prev => (prev ? prev + " " : "") + res.transcript);
        } catch (e: any) {
          setError(e?.message || "transcription failed");
        } finally {
          setTranscribing(false);
        }
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
    } catch {
      setError("Could not access microphone.");
    }
  };
  const stopRecording = () => { recRef.current?.stop(); setRecording(false); };

  // -- submit dispatch ------------------------------------------------------
  const submit = () => {
    const t = input.trim();
    if (!t || streaming) return;
    if (mode === "consensus") extractText(t);
    else sendChat(t);
  };
  const onSubmit = (e: React.FormEvent) => { e.preventDefault(); submit(); };
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };
  const reset = () => { setMessages([]); setInput(""); setError(null); };
  const empty = messages.length === 0;

  return (
    <div className="max-w-3xl mx-auto"
         onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
         onDragLeave={() => setDragOver(false)}
         onDrop={(e) => {
           e.preventDefault(); setDragOver(false);
           const f = e.dataTransfer.files?.[0]; if (f) handleFile(f);
         }}>
      {dragOver && (
        <div className="fixed inset-0 z-30 grid place-items-center bg-accent-softer/85 backdrop-blur-sm pointer-events-none">
          <div className="rounded-2xl border-2 border-dashed border-accent px-8 py-6 text-center bg-white shadow-cardHover">
            <div className="text-[32px] font-display font-semibold text-accent-deep">Drop to add</div>
            <div className="text-sm text-ink-200 mt-1.5 max-w-md">
              <span className="font-medium">PDFs</span> are parsed for structured data ·
              <span className="font-medium"> photos</span> get clinical-vision analysis or transcription
            </div>
          </div>
        </div>
      )}

      {empty ? <Hero ctx={ctx.data} /> : <ThreadHeader onReset={reset} count={messages.length} />}

      {!empty && (
        <div className="space-y-5 mb-5">
          {messages.map((m, i) => (
            m.role === "system"
              ? <IngestCard key={i} msg={m} onOpen={(id) => navigate(`/reports/${id}`)} />
              : <Bubble key={i} msg={m as any} streaming={streaming && i === messages.length - 1 && m.role === "assistant"} />
          ))}
          <div ref={threadEnd} />
        </div>
      )}

      <div className={clsx(empty ? "" : "sticky bottom-4 z-10")}>
        <form onSubmit={onSubmit} className="card shadow-cardHover overflow-hidden">
          <div className="relative">
            <textarea
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown}
              rows={empty ? 3 : 2}
              placeholder={
                mode === "consensus"
                  ? "Paste a structured report. Folio will run a 3-model ensemble and show field-level agreement."
                  : empty
                    ? "Tell Folio what's on your mind, or drop a PDF / photo…"
                    : "Type a reply, or drop a file anywhere on the page…"
              }
              className="w-full resize-none px-5 pt-4 pb-2 text-[15px] text-ink-100 placeholder:text-ink-400 focus:outline-none bg-transparent leading-relaxed"
              disabled={streaming || transcribing}
            />
            <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1">
              <div className="flex items-center gap-1.5">
                <ComposerBtn onClick={recording ? stopRecording : startRecording}
                              disabled={streaming || transcribing}
                              active={recording} title={recording ? "Stop & transcribe" : "Voice input"}>
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                    <rect x="9" y="3" width="6" height="13" rx="3" />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round"/>
                  </svg>
                </ComposerBtn>
                <ComposerBtn onClick={() => fileInputRef.current?.click()}
                              disabled={streaming || transcribing} title="Attach a PDF or image">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                    <path d="M21 12.5 12.5 21a5 5 0 1 1-7-7L14 5.5a3.5 3.5 0 0 1 5 5L10.5 19a2 2 0 1 1-3-3l8-8" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </ComposerBtn>
                <input ref={fileInputRef} type="file" accept="application/pdf,image/*" className="hidden"
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.currentTarget.value = ""; }} />
                {transcribing && <span className="text-[11.5px] text-ink-300 animate-pulse-soft">transcribing…</span>}
                {recording && <span className="text-[11.5px] text-alert-deep font-medium">recording — click to stop</span>}
              </div>

              <div className="flex items-center gap-2">
                <ModePill mode={mode} onChange={setMode} />
                <button type="submit" disabled={!input.trim() || streaming || transcribing}
                        className="btn btn-primary disabled:opacity-40 disabled:cursor-not-allowed">
                  {streaming
                    ? (mode === "consensus" ? "Extracting…" : "Thinking…")
                    : (mode === "consensus" ? <>Extract <span className="opacity-70">↵</span></> : <>Send <span className="opacity-70">↵</span></>)}
                </button>
              </div>
            </div>
          </div>
        </form>

        {error && (
          <div className="mt-3 rounded-xl border border-alert/30 bg-alert-softer px-3.5 py-2.5 text-[12.5px] text-alert-ink">
            <span className="font-medium">Couldn't reach Folio:</span> {error}
          </div>
        )}

        {empty && (
          <div className="mt-5">
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold mb-2">Try one of these</div>
            <div className="flex flex-wrap gap-2">
              {QUICK_PROMPTS.map((p, i) => (
                <button key={i} onClick={() => sendChat(p.text)}
                        className="chip hover:bg-accent-softer hover:border-accent/40 hover:text-accent-ink transition cursor-pointer">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------

function ModePill({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-white p-0.5 flex items-center gap-0.5"
         title="Standard: chat conversation · High-conf: 3-model ensemble extraction">
      <PillBtn active={mode === "standard"} onClick={() => onChange("standard")}>
        <Bolt /> Standard
      </PillBtn>
      <PillBtn active={mode === "consensus"} onClick={() => onChange("consensus")}>
        <Stack /> High-conf
      </PillBtn>
    </div>
  );
}

function PillBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
            className={clsx("flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-medium transition",
              active
                ? "bg-accent text-white shadow-glow"
                : "text-ink-200 hover:text-ink-100 hover:bg-ink-850")}>
      {children}
    </button>
  );
}

function Bolt() { return <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M13 3 4 14h7l-1 7 9-11h-7z" strokeLinejoin="round"/></svg>; }
function Stack() { return <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 18l9 5 9-5"/></svg>; }

function ComposerBtn({ children, onClick, disabled, active, title }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; active?: boolean; title?: string;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title}
      className={clsx("h-9 w-9 grid place-items-center rounded-lg transition border",
        active ? "bg-alert text-white border-alert animate-pulse-soft"
                : "bg-white border-ink-700 text-ink-200 hover:bg-accent-softer hover:border-accent/40 hover:text-accent-deep",
        disabled && "opacity-50 cursor-not-allowed")}>
      {children}
    </button>
  );
}

function Hero({ ctx }: { ctx: any }) {
  const greeting = timeGreeting();
  const name = displayName().split(/\s+/)[0];  // first name only in the headline
  return (
    <div className="mb-5 max-w-2xl">
      <div className="text-[10.5px] uppercase tracking-[0.22em] text-accent-deep font-semibold">{greeting}</div>
      <h1 className="font-display text-[34px] sm:text-[40px] leading-[1.05] font-semibold tracking-tight text-ink-50 mt-1.5">
        How are you feeling today, <span className="text-accent-deep">{name}</span>?
      </h1>
      <p className="text-[14.5px] text-ink-200 mt-3 leading-relaxed">
        Talk to Folio about anything — a symptom, a question about your record, or just a check-in. Drop a PDF or photo to add it to your record. Flip the mode pill to <span className="font-medium text-accent-deep">High-conf</span> to run a 3-LLM ensemble extraction on a structured report.
      </p>
      {ctx && <ContextStrip ctx={ctx} />}
    </div>
  );
}

function ContextStrip({ ctx }: { ctx: any }) {
  const items = [
    { label: "Conditions", value: ctx.active_conditions ?? 0, link: "/overview" },
    { label: "Meds",       value: ctx.active_medications ?? 0, link: "/overview" },
    { label: "Last read",  value: ctx.last_vital_at  ? fmtRelative(ctx.last_vital_at)  : "—", link: "/timeline" },
    { label: "Last rep.",  value: ctx.last_report_at ? fmtRelative(ctx.last_report_at) : "—", link: "/timeline" },
  ];
  const noKey = !ctx.has_anthropic && !ctx.has_openai;
  return (
    <div className="mt-4">
      <div className="flex items-center divide-x divide-ink-700 rounded-xl border border-ink-700 bg-white">
        {items.map(i => (
          <Link key={i.label} to={i.link}
                className="flex-1 px-3 py-2 hover:bg-accent-softer/40 transition first:rounded-l-xl last:rounded-r-xl">
            <div className="text-[9.5px] uppercase tracking-[0.14em] text-ink-300">{i.label}</div>
            <div className="text-[13px] font-display font-semibold text-ink-50 num">{i.value}</div>
          </Link>
        ))}
      </div>
      {noKey && (
        <div className="rounded-xl border border-warn/30 bg-warn-softer px-3.5 py-2 text-[12px] text-warn-ink mt-3">
          <span className="font-medium">No model API key.</span> Add <code className="font-mono">ANTHROPIC_API_KEY</code> to <code className="font-mono">.env</code> and restart the backend.
        </div>
      )}
    </div>
  );
}

function ThreadHeader({ onReset, count }: { onReset: () => void; count: number }) {
  return (
    <div className="flex items-center justify-between mb-5">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Conversation</div>
        <h2 className="font-display text-[22px] font-semibold tracking-tight text-ink-50 mt-1">
          {count} message{count === 1 ? "" : "s"}
        </h2>
      </div>
      <button onClick={onReset} className="btn btn-ghost text-[12px] py-1.5 px-2.5">+ Start fresh</button>
    </div>
  );
}

function Bubble({ msg, streaming }: { msg: any; streaming: boolean }) {
  const isUser = msg.role === "user";
  return (
    <div className={clsx("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      {!isUser && <Avatar />}
      <div className="max-w-[78%]">
        <div className={clsx("rounded-2xl px-4 py-3 leading-relaxed",
          isUser
            ? "bg-accent text-white shadow-glow"
            : "bg-white border border-ink-700 text-ink-100 shadow-card")}>
          <div className="text-[14.5px] whitespace-pre-wrap">
            {msg.content || (streaming && <Typing />)}
            {streaming && msg.content && <Caret />}
          </div>
        </div>
        {!isUser && msg.citations?.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold">cited</span>
            {msg.citations.map((c: Citation, i: number) => (
              <Link key={i} to={`/reports/${c.report_id}`}
                    className="chip chip-info hover:bg-info-soft transition"
                    title={`similarity ${c.score.toFixed(2)}`}>
                {fmtDate(c.uploaded_at)} · {c.input_type}
                <span className="num font-mono ml-1 text-[9.5px] opacity-70">·{c.score.toFixed(2)}</span>
              </Link>
            ))}
            {msg.ragMs != null && <span className="text-[10.5px] text-ink-300 font-mono num">retrieved in {Math.round(msg.ragMs)}ms</span>}
          </div>
        )}
      </div>
      {isUser && <UserAvatar />}
    </div>
  );
}

function IngestCard({ msg, onOpen }: { msg: IngestCardMsg; onOpen: (id: string) => void }) {
  const consensus = msg.consensus;
  return (
    <div className="flex gap-3">
      <Avatar />
      <div className="max-w-[78%] w-full card overflow-hidden">
        <div className="px-4 py-3 border-b border-ink-700 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">
              {msg.mode === "consensus" ? "Consensus extract" : "Ingest"}
            </span>
            {msg.mode === "consensus" && <span className="chip chip-info">3-model</span>}
            {msg.status === "running" && <span className="chip chip-accent"><span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft"/> processing</span>}
            {msg.status === "done" && <span className="chip chip-good">complete</span>}
            {msg.status === "error" && <span className="chip chip-alert">error</span>}
            {msg.sourceLabel && <span className="text-[11px] text-ink-300 font-mono truncate">· {msg.sourceLabel}</span>}
          </div>
          {msg.report?.report_id && (
            <button onClick={() => onOpen(msg.report.report_id)} className="text-[12px] link shrink-0">open detail →</button>
          )}
        </div>
        <div className="p-4 space-y-3">
          {msg.stages?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {msg.stages.map((s, i) => (
                <span key={i} className="chip font-mono text-[10px]">
                  {s.stage} <span className="text-accent-deep ml-1 num">{s.ms.toFixed(0)}ms</span>
                </span>
              ))}
            </div>
          )}
          {msg.report && <IngestSummary report={msg.report} />}
          {consensus && <ConsensusMini meta={consensus} />}
          {msg.error && <div className="rounded-lg border border-alert/30 bg-alert-softer p-3 text-[13px] text-alert-ink">{msg.error}</div>}
        </div>
      </div>
    </div>
  );
}

function IngestSummary({ report }: { report: any }) {
  const counts: [string, number][] = [
    ["diagnoses",   report.diagnoses?.length   || 0],
    ["medications", report.medications?.length || 0],
    ["vitals",      report.vitals?.length      || 0],
    ["labs",        report.labs?.length        || 0],
    ["symptoms",    report.symptoms?.length    || 0],
    ["red flags",   report.red_flags?.length   || 0],
  ].filter(([, n]) => n > 0);
  return (
    <div>
      {report.raw_summary && (
        <div className="rounded-lg border border-accent/25 bg-accent-softer p-3 text-[13px] text-accent-ink leading-relaxed mb-3">
          {report.raw_summary}
        </div>
      )}
      {counts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {counts.map(([k, n]) => <span key={k} className="chip">{n} {k}</span>)}
        </div>
      )}
    </div>
  );
}

function ConsensusMini({ meta }: { meta: any }) {
  const fields: [string, any[]][] = Object.entries(meta.fields || {});
  const overall = Math.round((meta.overall_agreement || 0) * 100);
  return (
    <div className="rounded-lg border border-info/25 bg-info-softer/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] uppercase tracking-[0.14em] text-info-ink font-semibold">consensus</div>
        <div className="font-display text-[14px] font-semibold text-info-ink num">{overall}% agreement</div>
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-ink-300 mb-2">
        {meta.models_succeeded.map((m: string) => <span key={m} className="chip chip-good font-mono text-[9.5px]">{m}</span>)}
        {meta.models_failed?.map((f: any) => <span key={f.model} className="chip chip-alert font-mono text-[9.5px]" title={f.error}>{f.model} ✗</span>)}
      </div>
      <div className="space-y-1">
        {fields.filter(([_, c]) => c.length > 0).slice(0, 4).flatMap(([key, clusters]) =>
          clusters.slice(0, 2).map((c: any, i: number) => (
            <div key={`${key}-${i}`} className="flex items-center gap-2.5">
              <div className="text-[11.5px] text-ink-100 flex-1 truncate font-mono">{c.value_key}</div>
              <div className="flex items-center gap-1">
                {(["anthropic","openai","gemini"] as const).map(p => (
                  <span key={p} title={p} className={clsx("h-1.5 w-1.5 rounded-full",
                    c.providers?.includes(p) ? providerColor(p) : "bg-ink-700")}/>
                ))}
              </div>
              <div className={clsx("text-[10.5px] num font-mono w-9 text-right",
                c.confidence >= 0.99 ? "text-good-deep" : c.confidence >= 0.66 ? "text-warn-deep" : "text-alert-deep")}>
                {Math.round(c.confidence * 100)}%
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function providerColor(p: string) {
  return p === "anthropic" ? "bg-warn-deep"
       : p === "openai"    ? "bg-good-deep"
       : p === "gemini"    ? "bg-info-deep"
       : "bg-ink-300";
}

function Avatar() {
  return (
    <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-accent to-accent-deep grid place-items-center shadow-glow shrink-0">
      <svg viewBox="0 0 32 32" className="h-5 w-5"><path d="M5 16 L10 16 L12 10 L16 22 L18 16 L27 16" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
    </div>
  );
}
function UserAvatar() {
  return <div className="h-9 w-9 rounded-xl bg-info-soft grid place-items-center text-info-ink font-display text-[13px] font-semibold shrink-0">{initials()}</div>;
}
function Typing() {
  return (
    <span className="inline-flex gap-1.5 items-center py-0.5">
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{animationDelay:"0ms"}}/>
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{animationDelay:"200ms"}}/>
      <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft" style={{animationDelay:"400ms"}}/>
    </span>
  );
}
function Caret() { return <span className="inline-block w-1 h-4 ml-0.5 bg-accent align-middle animate-pulse-soft" />; }

// ----- helpers ---------------------------------------------------------------
function tryParse(s: string): string | null {
  try { const v = JSON.parse(s); if (typeof v === "string") return v; } catch {}
  return null;
}
function timeGreeting(): string {
  const h = new Date().getHours();
  if (h < 5)  return "Late night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Good night";
}
function updateLast(prev: ChatMsg[], role: ChatMsg["role"], updater: (m: any) => any): ChatMsg[] {
  const out = [...prev];
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i].role === role) { out[i] = updater(out[i]); break; }
  }
  return out;
}
function updateLastIngest(prev: ChatMsg[], updater: (m: IngestCardMsg) => IngestCardMsg): ChatMsg[] {
  const out = [...prev];
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i].role === "system" && (out[i] as any).kind === "ingest") {
      out[i] = updater(out[i] as IngestCardMsg);
      break;
    }
  }
  return out;
}
