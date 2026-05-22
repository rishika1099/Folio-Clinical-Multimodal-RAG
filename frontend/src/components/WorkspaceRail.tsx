import { useState } from "react";
import clsx from "clsx";

import { api, API_BASE } from "../lib/api";
import { postSSE } from "../lib/sse";

export type IngestMode = "standard" | "consensus";

export type IngestEvent =
  | { kind: "started"; mode: IngestMode; sourceLabel: string }
  | { kind: "stage"; stage: string; ms: number }
  | { kind: "report"; report: any; consensus?: any }
  | { kind: "error"; message: string }
  | { kind: "done" };

interface Props {
  /** Called as the ingest unfolds so the chat thread can render a card per stage. */
  onEvent: (e: IngestEvent) => void;
  /** Notify the parent to refetch overview / timeline / snapshot. */
  onIngestComplete: () => void;
  /** Optional callback to expose the current mode upward — useful if the parent
   *  wants the chat composer's file uploads to honour the same toggle. */
  onModeChange?: (mode: IngestMode) => void;
}

export default function WorkspaceRail({ onEvent, onIngestComplete, onModeChange }: Props) {
  const [mode, setModeState] = useState<IngestMode>("standard");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const setMode = (m: IngestMode) => { setModeState(m); onModeChange?.(m); };

  const submitText = async () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    onEvent({ kind: "started", mode, sourceLabel: t.length > 60 ? t.slice(0, 60) + "…" : t });
    try {
      if (mode === "consensus") {
        const res = await api<any>("/api/consensus", {
          method: "POST",
          body: JSON.stringify({ text: t, input_type: "text" }),
        });
        onEvent({ kind: "report", report: res.report, consensus: res.consensus });
      } else {
        await postSSE(`${API_BASE}/api/ingest/text`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: t }),
        }, (e) => {
          if (e.event === "stage") onEvent({ kind: "stage", ...JSON.parse(e.data) });
          else if (e.event === "report") onEvent({ kind: "report", report: JSON.parse(e.data) });
          else if (e.event === "error") onEvent({ kind: "error", message: JSON.parse(e.data).message });
        });
      }
      onEvent({ kind: "done" });
      setText("");
      onIngestComplete();
    } catch (err: any) {
      onEvent({ kind: "error", message: err?.message || "ingest failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="space-y-3 xl:sticky xl:top-20">
      <div className="flex items-center justify-between px-1">
        <div className="text-[10px] uppercase tracking-[0.2em] text-ink-300 font-semibold">Ingest lab</div>
        <span className="text-[10px] text-ink-400">paste · choose mode</span>
      </div>

      <ModeToggle mode={mode} onChange={setMode} />

      <div className="card overflow-hidden">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Paste a structured report here…  e.g. Quarterly visit. A1C 7.2, BP 142/92, started Metformin 500mg BID."
          disabled={busy}
          className="w-full resize-none px-3.5 py-3 text-[13px] text-ink-100 placeholder:text-ink-400 focus:outline-none bg-transparent leading-relaxed"
        />
        <div className="flex items-center justify-between gap-2 px-3 pb-2.5 pt-1 border-t border-ink-700/70">
          <span className="text-[10.5px] text-ink-300 font-mono">
            {mode === "consensus" ? "→ /api/consensus · 3-LLM ensemble" : "→ /api/ingest/text · streamed"}
          </span>
          <button onClick={submitText} disabled={busy || !text.trim()}
                  className="btn btn-primary text-[12px] py-1 px-2.5 disabled:opacity-40 disabled:cursor-not-allowed">
            {busy ? "Working…" : <>Extract <span className="opacity-70 ml-0.5">↵</span></>}
          </button>
        </div>
      </div>

      <p className="text-[10.5px] text-ink-300 leading-snug px-1">
        For PDFs, photos, and voice notes, use the attach button in the chat composer on the left — they ingest in standard mode and stream their result inline as a card.
      </p>
    </aside>
  );
}

function ModeToggle({ mode, onChange }: { mode: IngestMode; onChange: (m: IngestMode) => void }) {
  return (
    <div className="rounded-xl border border-ink-700 bg-white p-1 grid grid-cols-2 gap-1">
      <ModeBtn active={mode === "standard"} onClick={() => onChange("standard")}
               title="Standard" sub="~1.5s · 1 model">
        <Bolt />
      </ModeBtn>
      <ModeBtn active={mode === "consensus"} onClick={() => onChange("consensus")}
               title="High-conf" sub="~6–10s · 3 models">
        <Stack />
      </ModeBtn>
    </div>
  );
}

function ModeBtn({ active, onClick, title, sub, children }: {
  active: boolean; onClick: () => void; title: string; sub: string; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick}
            className={clsx("flex items-center gap-2 rounded-lg px-2.5 py-2 transition text-left",
              active
                ? "bg-accent-softer shadow-[inset_0_0_0_1px_rgba(122,171,165,0.35)]"
                : "hover:bg-ink-850")}>
      <span className={clsx("h-7 w-7 rounded-md grid place-items-center shrink-0",
        active ? "bg-accent text-white" : "bg-ink-850 text-ink-200")}>{children}</span>
      <div className="min-w-0">
        <div className={clsx("text-[12.5px] font-medium leading-tight", active ? "text-accent-ink" : "text-ink-100")}>{title}</div>
        <div className="text-[10px] text-ink-300 leading-tight num font-mono">{sub}</div>
      </div>
    </button>
  );
}

function Bolt() { return <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M13 3 4 14h7l-1 7 9-11h-7z" strokeLinejoin="round"/></svg>; }
function Stack() { return <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 18l9 5 9-5"/></svg>; }

