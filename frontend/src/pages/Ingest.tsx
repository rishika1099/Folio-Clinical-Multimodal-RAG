import { useRef, useState } from "react";
import imageCompression from "browser-image-compression";
import clsx from "clsx";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Card } from "../components/Card";
import { SeverityChip } from "../components/Severity";
import { postSSE } from "../lib/sse";
import { parsePartial } from "../lib/partialJson";
import { api, API_BASE } from "../lib/api";
import { friendlyError } from "../lib/errors";

type Mode = "text" | "pdf" | "image" | "voice";

const MODE_LABELS: Record<Mode, { title: string; sub: string; icon: React.ReactNode }> = {
  text:  { title: "Free text",   sub: "Paste a report or write what's going on.", icon: <span className="font-mono">¶</span> },
  pdf:   { title: "PDF",         sub: "Lab reports, discharge summaries, imaging.", icon: <span className="font-mono">⌥</span> },
  image: { title: "Photo",       sub: "Skin condition, eye, wound — or a paper report.", icon: <span className="font-mono">▢</span> },
  voice: { title: "Voice note",  sub: "Describe symptoms or read a report aloud.", icon: <span className="font-mono">○</span> },
};

export default function IngestPage() {
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stages, setStages] = useState<{stage: string; ms: number}[]>([]);
  const [buf, setBuf] = useState("");
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [highConfidence, setHighConfidence] = useState(false);
  const [consensusMeta, setConsensusMeta] = useState<any>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const reset = () => { setStages([]); setBuf(""); setReport(null); setError(null); setConsensusMeta(null); };

  const start = async (req: { url: string; init: RequestInit }) => {
    reset();
    setStreaming(true);
    try {
      await postSSE(`${API_BASE}${req.url}`, req.init, (e) => {
        if (e.event === "stage") setStages(s => [...s, JSON.parse(e.data)]);
        else if (e.event === "token") setBuf(b => b + (tryUnpack(e.data) ?? e.data));
        else if (e.event === "report") setReport(JSON.parse(e.data));
        else if (e.event === "error") setError(friendlyError(new Error(JSON.parse(e.data).message)));
        else if (e.event === "done") {
          qc.invalidateQueries({ queryKey: ["overview"] });
          qc.invalidateQueries({ queryKey: ["timeline"] });
          qc.invalidateQueries({ queryKey: ["suggestions"] });
        }
      });
    } catch (err: any) {
      setError(friendlyError(err));
    } finally {
      setStreaming(false);
    }
  };

  const submitText = async () => {
    if (!text.trim()) return;
    if (highConfidence) {
      reset();
      setStreaming(true);
      try {
        const res = await api<any>("/api/consensus", {
          method: "POST",
          body: JSON.stringify({ text, input_type: "text" }),
        });
        setReport(res.report);
        setConsensusMeta(res.consensus);
        qc.invalidateQueries({ queryKey: ["overview"] });
        qc.invalidateQueries({ queryKey: ["timeline"] });
        qc.invalidateQueries({ queryKey: ["chat-snapshot"] });
      } catch (err: any) {
        setError(friendlyError(err));
      } finally {
        setStreaming(false);
      }
      return;
    }
    start({
      url: "/api/ingest/text",
      init: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) },
    });
  };

  const submitFile = async (file: File, kind: "pdf" | "image") => {
    let f: File | Blob = file;
    if (kind === "image") {
      try {
        f = await imageCompression(file, { maxSizeMB: 1, maxWidthOrHeight: 1024 });
      } catch {}
    }
    const fd = new FormData();
    fd.append("file", f, file.name);
    start({ url: `/api/ingest/${kind}`, init: { method: "POST", body: fd } });
  };

  const live = parsePartial(buf);
  const showSamples = mode === "text" && !text && !streaming && !report;

  return (
    <div className="space-y-7">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Ingest</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Add a report</h1>
        <p className="text-sm text-ink-200 mt-1.5 max-w-xl">
          Choose any input. Folio scrubs PII, runs the right model for the modality, and renders the structured extraction field-by-field as the model streams.
        </p>
      </div>

      <ConfidenceToggle on={highConfidence} onChange={setHighConfidence} />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {(Object.keys(MODE_LABELS) as Mode[]).map(m => {
          const meta = MODE_LABELS[m];
          const active = mode === m;
          return (
            <button key={m} onClick={() => { setMode(m); reset(); }}
              className={clsx(
                "text-left rounded-2xl border p-4 transition",
                active
                  ? "border-accent/40 bg-accent-softer shadow-glow"
                  : "border-ink-700 bg-white hover:border-accent/30 hover:bg-accent-softer/50"
              )}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className={clsx("h-7 w-7 grid place-items-center rounded-lg",
                  active ? "bg-accent text-white" : "bg-ink-850 text-ink-100")}>
                  {meta.icon}
                </span>
                <span className={clsx("font-medium", active ? "text-accent-ink" : "text-ink-50")}>{meta.title}</span>
              </div>
              <div className="text-[12px] text-ink-300 leading-snug">{meta.sub}</div>
            </button>
          );
        })}
      </div>

      <Card title={`Input · ${MODE_LABELS[mode].title}`} eyebrow="Step 1">
        {mode === "text" && (
          <>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="e.g. BP this morning 144/92, persistent morning headaches for 2 weeks. Currently on lisinopril 20mg."
              className="input h-44 resize-none"
            />
            {showSamples && (
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="text-[11px] text-ink-300 self-center">Try:</span>
                {SAMPLES.map((s, i) => (
                  <button key={i} onClick={() => setText(s)} className="chip hover:bg-accent-softer hover:border-accent/30">
                    {s.slice(0, 38)}…
                  </button>
                ))}
              </div>
            )}
            <div className="mt-3 flex justify-end">
              <button onClick={submitText} disabled={streaming || !text.trim()}
                className="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed">
                {streaming ? "Streaming…" : "Extract →"}
              </button>
            </div>
          </>
        )}

        {mode === "pdf" && (
          <FileDrop accept="application/pdf"
                    label="PDF report"
                    hint="Native text is parsed deterministically; scanned PDFs are routed to vision OCR."
                    disabled={streaming}
                    onFile={(f) => submitFile(f, "pdf")} />
        )}
        {mode === "image" && (
          <>
            <div className="mb-3 rounded-xl border border-info/30 bg-info-softer px-3.5 py-2.5 text-[12.5px] text-info-ink leading-relaxed">
              <span className="font-medium">Clinical-vision analysis.</span> Folio describes what's visible — skin lesions, eyes, wounds, paper reports, prescription labels — and populates the same structured schema used everywhere else. Visible findings go into <code className="font-mono">symptoms</code>; concerning features into <code className="font-mono">red_flags</code>; differential considerations end up in the summary with hedged language.
            </div>
            <FileDrop accept="image/*"
                      label="photo of a body part or paper report"
                      hint="Skin condition, eye, wound, scan of a lab, prescription bottle — anything visual."
                      disabled={streaming}
                      onFile={(f) => submitFile(f, "image")} />
          </>
        )}

        {mode === "voice" && <VoiceCapture disabled={streaming} onClip={(blob) => {
          const fd = new FormData(); fd.append("file", blob, "clip.webm");
          start({ url: "/api/ingest/voice", init: { method: "POST", body: fd } });
        }} />}
      </Card>

      {consensusMeta && <ConsensusPanel meta={consensusMeta} />}

      {(streaming || stages.length > 0 || report || error) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card title="Pipeline" eyebrow="Step 2 · live"
                action={streaming ? <span className="chip chip-accent"><span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-soft"/> streaming</span> : <span className="chip chip-good">complete</span>}>
            {streaming && <div className="streaming-bar h-0.5 -mt-1 mb-3 rounded-full" />}
            <ol className="space-y-1.5 text-[12.5px]">
              {stages.map((s, i) => (
                <li key={i} className="flex justify-between items-center font-mono py-1 px-2 rounded-md odd:bg-ink-900/70">
                  <span className="text-ink-200">{s.stage}</span>
                  <span className="text-accent-deep num">{s.ms.toFixed(0)} ms</span>
                </li>
              ))}
              {!stages.length && <li className="text-ink-300 text-sm py-2">Waiting for first stage…</li>}
            </ol>
            {error && <div className="mt-3 rounded-xl border border-alert/30 bg-alert-softer p-3 text-[13px] text-alert-ink">
              <div className="font-medium mb-0.5">Pipeline error</div>{error}
            </div>}
          </Card>

          <Card title="Extraction" eyebrow="Step 3 · structured output"
                action={report && <button onClick={() => navigate(`/reports/${report.report_id}`)} className="text-[12px] link">open detail →</button>}>
            <LiveExtraction live={live} report={report} />
          </Card>
        </div>
      )}
    </div>
  );
}

const SAMPLES = [
  "Annual physical exam. BP 132/86, HR 78. HbA1c 6.0% (pre-diabetic). Continued lisinopril 10mg daily.",
  "Voice note from Tuesday: still getting morning headaches. Home BP cuff: 146 over 94, two readings.",
  "Lab results: HbA1c 7.5%, LDL 142, Creatinine 1.0. Started Metformin 500mg BID.",
];

function tryUnpack(s: string): string | null {
  try {
    const parsed = JSON.parse(s);
    if (typeof parsed === "string") return parsed;
    if (parsed && typeof parsed === "object" && "transcript" in parsed) return "";
  } catch {}
  return null;
}

function FileDrop({ accept, label, hint, disabled, onFile }: {
  accept: string; label: string; hint?: string; disabled?: boolean; onFile: (f: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault(); setDragging(false);
        const f = e.dataTransfer.files?.[0];
        if (f) { setFile(f); onFile(f); }
      }}
      className={clsx(
        "relative rounded-2xl border-2 border-dashed p-10 text-center transition",
        dragging ? "border-accent bg-accent-softer" : "border-ink-700 bg-ink-900/40 hover:bg-accent-softer/40 hover:border-accent/40",
        disabled && "opacity-50 pointer-events-none"
      )}
    >
      <div className="mx-auto mb-3 h-10 w-10 rounded-full bg-accent-soft text-accent-deep grid place-items-center">
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7">
          <path d="M12 4v12m0 0-4-4m4 4 4-4M4 18v2h16v-2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>
      <input ref={inputRef} type="file" accept={accept} className="hidden"
             onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); onFile(f); } }} />
      <div className="text-[14px] text-ink-100 font-medium mb-1">Drop a {label} here</div>
      <div className="text-[12px] text-ink-300 mb-3">{hint || "or click below to browse · max 1 MB / 1024px (auto-compressed)"}</div>
      <button className="btn btn-ghost" onClick={() => inputRef.current?.click()}>Choose file</button>
      {file && <div className="mt-3 text-[12px] text-ink-300 font-mono">{file.name}</div>}
    </div>
  );
}

function VoiceCapture({ onClip, disabled }: { onClip: (blob: Blob) => void; disabled?: boolean }) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const tickRef = useRef<number | null>(null);

  // iPhone Safari ships no WebM encoder — pick a mime the browser actually
  // supports, falling back to MP4 (which Whisper also accepts).
  const pickMime = (): string => {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4;codecs=mp4a.40.2", "audio/mp4"];
    for (const c of candidates) {
      // @ts-expect-error MediaRecorder type lacks isTypeSupported in older lib.dom
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(c)) return c;
    }
    return "";
  };

  const start = async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        alert("Your browser doesn't support voice recording. Try Chrome, Edge, or recent Safari.");
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || mime || "audio/webm" });
        stream.getTracks().forEach(t => t.stop());
        if (blob.size < 1000) { alert("Recording was too quiet. Try again."); return; }
        onClip(blob);
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
      setElapsed(0);
      tickRef.current = window.setInterval(() => setElapsed(e => e + 1), 1000);
    } catch (e: any) {
      const name = e?.name || "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        alert("Microphone access was denied. Allow it in your browser settings and try again.");
      } else if (name === "NotFoundError") {
        alert("No microphone was found on this device.");
      } else {
        alert("We couldn't start recording. Try again, or upload an audio file instead.");
      }
    }
  };
  const stop = () => {
    recRef.current?.stop();
    setRecording(false);
    if (tickRef.current) clearInterval(tickRef.current);
  };

  return (
    <div className="rounded-2xl border border-ink-700 bg-ink-900/60 p-10 text-center">
      <div className="relative mx-auto h-24 w-24">
        <div className={clsx("absolute inset-0 rounded-full",
          recording ? "bg-alert/20 animate-pulse-soft" : "bg-accent/15")} />
        <div className={clsx("absolute inset-2 rounded-full grid place-items-center",
          recording ? "bg-alert text-white" : "bg-white text-accent-deep border border-accent/40")}>
          <svg viewBox="0 0 24 24" className="h-10 w-10" fill="none" stroke="currentColor" strokeWidth="1.6">
            <rect x="9" y="3" width="6" height="13" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        </div>
      </div>
      <div className="mt-4 font-mono num text-ink-200 text-sm tracking-widest">
        {recording ? `REC  ${String(Math.floor(elapsed/60)).padStart(2,"0")}:${String(elapsed%60).padStart(2,"0")}` : "READY"}
      </div>
      <div className="mt-5">
        {!recording
          ? <button onClick={start} disabled={disabled} className="btn btn-primary">Start recording</button>
          : <button onClick={stop} className="btn btn-ghost">Stop & transcribe</button>}
      </div>
      <div className="mt-3 text-[11.5px] text-ink-300">Audio is sent to Whisper for transcription, then routed to the extraction model.</div>
    </div>
  );
}

function LiveExtraction({ live, report }: { live: any; report: any }) {
  const data = report || live;
  if (!data) return (
    <div className="text-sm text-ink-300 py-3">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-accent animate-pulse-soft" />
        <span>Awaiting first token from extraction model…</span>
      </div>
    </div>
  );

  const sections: { key: string; label: string; render: (v: any) => React.ReactNode }[] = [
    { key: "diagnoses", label: "Diagnoses", render: (arr) => arr?.map?.((d: any, i: number) => (
        <Row key={i} title={d.condition || "—"} sub={`${d.icd10 || "—"} · ${d.status || "—"}`}
             right={d.confidence != null && <span className="num font-mono text-accent-deep">{Math.round(d.confidence*100)}%</span>} />
    )) },
    { key: "medications", label: "Medications", render: (arr) => arr?.map?.((m: any, i: number) => (
        <Row key={i} title={m.name || "—"} sub={`${m.dose || ""} ${m.frequency || ""}`.trim() || "—"} right={m.purpose} />
    )) },
    { key: "vitals", label: "Vitals", render: (arr) => arr?.map?.((v: any, i: number) => (
        <Row key={i} title={(v.type || "").toString().toUpperCase()} sub={v.recorded_at} right={<span className="font-mono num">{v.value} {v.unit || ""}</span>} />
    )) },
    { key: "labs", label: "Labs", render: (arr) => arr?.map?.((l: any, i: number) => (
        <Row key={i} title={l.test} sub={l.reference_range && `ref ${l.reference_range}`} right={
          <span className="flex items-center gap-2"><span className="font-mono num">{l.value} {l.unit}</span><SeverityChip s={l.flag||"normal"} /></span>
        } />
    )) },
    { key: "symptoms", label: "Symptoms", render: (arr) => arr?.map?.((s: any, i: number) => (
        <Row key={i} title={s.description} sub={s.onset} right={<SeverityChip s={s.severity || "mild"} />} />
    )) },
    { key: "red_flags", label: "Red flags", render: (arr) => arr?.map?.((r: any, i: number) => (
        <Row key={i} title={r.finding} sub={r.reason} right={<SeverityChip s={r.urgency || "routine"} />} />
    )) },
  ];

  return (
    <div className="space-y-4">
      {data.raw_summary && (
        <div className="rounded-xl border border-accent/25 bg-accent-softer p-3.5 text-[13px] text-accent-ink leading-relaxed">
          {data.raw_summary}
        </div>
      )}
      {sections.map(({ key, label, render }) => {
        const arr = data[key];
        if (!arr || (Array.isArray(arr) && !arr.length)) return null;
        return (
          <div key={key}>
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold mb-1.5">{label}</div>
            <div className="divide-y divide-ink-700">{render(arr)}</div>
          </div>
        );
      })}
    </div>
  );
}

function Row({ title, sub, right }: { title: React.ReactNode; sub?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="py-2 flex items-start justify-between gap-3">
      <div>
        <div className="text-[14px] text-ink-100 capitalize font-medium">{title}</div>
        {sub && <div className="text-[11.5px] text-ink-300 mt-0.5">{sub}</div>}
      </div>
      <div className="text-[12.5px] text-ink-200 whitespace-nowrap pt-0.5">{right}</div>
    </div>
  );
}

function ConfidenceToggle({ on, onChange }: { on: boolean; onChange: (b: boolean) => void }) {
  return (
    <div className="card card-pad flex items-start gap-4">
      <button onClick={() => onChange(!on)}
              className={clsx("relative h-7 w-12 rounded-full transition shrink-0",
                on ? "bg-accent" : "bg-ink-700")}>
        <span className={clsx("absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all",
          on ? "left-[22px]" : "left-0.5")}/>
      </button>
      <div className="flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <div className="text-[14.5px] font-medium text-ink-50">High-confidence mode</div>
          <span className="chip chip-info">multi-LLM consensus</span>
        </div>
        <div className="text-[12.5px] text-ink-200 leading-relaxed">
          Off: single safety-tuned model (Claude Sonnet 4.5, ~2s, streaming) — picked for its low hallucination rate on doses and lab values. On: parallel ensemble across Sonnet, GPT-4.1, and Gemini Pro with field-level vector clustering and per-field agreement scoring (~6–10s, no streaming). Use this when the report is high-stakes.
        </div>
      </div>
    </div>
  );
}

function ConsensusPanel({ meta }: { meta: any }) {
  const fields: [string, any[]][] = Object.entries(meta.fields || {});
  return (
    <div className="card card-pad">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Consensus run</div>
          <div className="font-display text-[18px] font-semibold text-ink-50 mt-0.5">
            {Math.round(meta.overall_agreement * 100)}% overall agreement
            <span className="text-[12px] text-ink-300 font-mono num font-normal ml-2">across {meta.n_models} models · {Math.round(meta.elapsed_ms)}ms</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {meta.models_succeeded.map((m: string) => <span key={m} className="chip chip-good font-mono text-[10px]">{m}</span>)}
          {meta.models_failed?.map((f: any) => <span key={f.model} className="chip chip-alert font-mono text-[10px]" title={f.error}>{f.model} ✗</span>)}
        </div>
      </div>

      <div className="space-y-3">
        {fields.filter(([_, clusters]) => clusters.length > 0).map(([field, clusters]) => (
          <div key={field}>
            <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold mb-1.5">{field}</div>
            <div className="space-y-1">
              {clusters.map((c: any, i: number) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="text-[12.5px] text-ink-100 flex-1 truncate font-mono">{c.value_key}</div>
                  <div className="flex items-center gap-1">
                    {(["anthropic","openai","gemini"] as const).map(p => (
                      <span key={p} title={p} className={clsx("h-2 w-2 rounded-full",
                        c.providers.includes(p) ? providerColor(p) : "bg-ink-700")}/>
                    ))}
                  </div>
                  <div className={clsx("text-[11px] num font-mono w-12 text-right",
                    c.confidence >= 0.99 ? "text-good-deep" : c.confidence >= 0.66 ? "text-warn-deep" : "text-alert-deep")}>
                    {Math.round(c.confidence * 100)}%
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-3 text-[10.5px] text-ink-300">
        <Legend c="bg-warn-deep"  l="Anthropic" />
        <Legend c="bg-good-deep"  l="OpenAI" />
        <Legend c="bg-info-deep"  l="Gemini" />
        <span className="ml-auto">Agreement = unique providers / models succeeded.</span>
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
function Legend({ c, l }: { c: string; l: string }) {
  return <span className="flex items-center gap-1"><span className={"h-2 w-2 rounded-full " + c}/>{l}</span>;
}
