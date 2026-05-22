import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { Card, StatTile } from "../components/Card";
import { fmtRelative } from "../lib/format";

export default function DevPage() {
  const routes = useQuery({ queryKey: ["routes"], queryFn: () => api("/api/dev/routes") });
  const lat = useQuery({ queryKey: ["latency"], queryFn: () => api("/api/dev/latency") });

  const summary = lat.data?.summary || {};

  return (
    <div className="space-y-7">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Engineering</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Dev panel</h1>
        <p className="text-sm text-ink-200 mt-1.5">Per-stage latency, model routing decisions, hot-path diagnostics. Use this to debug the production AI system.</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatTile label="Reports" value={summary.n ?? "—"} accent="info" hint="instrumented" />
        <StatTile label="p50" value={summary.p50_ms != null ? `${summary.p50_ms.toFixed(0)}` : "—"} hint="ms" accent={tone(summary.p50_ms, [2000, 3000])} />
        <StatTile label="p95" value={summary.p95_ms != null ? `${summary.p95_ms.toFixed(0)}` : "—"} hint="ms" accent={tone(summary.p95_ms, [3000, 5000])} />
        <StatTile label="p99" value={summary.p99_ms != null ? `${summary.p99_ms.toFixed(0)}` : "—"} hint="ms" accent={tone(summary.p99_ms, [5000, 8000])} />
      </div>

      <Card title="Model routing" eyebrow="Multi-model strategy">
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">
                <th className="text-left font-semibold py-2 px-2">Task</th>
                <th className="text-left font-semibold py-2 px-2">Primary</th>
                <th className="text-left font-semibold py-2 px-2">Fallback</th>
                <th className="text-left font-semibold py-2 px-2">Justification</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700">
              {routes.data?.routes?.map((r: any) => (
                <tr key={r.task} className="align-top">
                  <td className="py-3 px-2 font-medium text-ink-100">{r.task}</td>
                  <td className="py-3 px-2"><Provider p={r.primary} primary /></td>
                  <td className="py-3 px-2"><Provider p={r.fallback} /></td>
                  <td className="py-3 px-2 text-[12.5px] text-ink-200 leading-relaxed max-w-md">{r.primary.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Recent requests" eyebrow="Latency per stage">
        {!lat.data?.reports?.length ? <div className="text-sm text-ink-300 py-3">No instrumented requests yet. Run an ingest to populate.</div> :
          <div className="space-y-2.5">
            {lat.data.reports.map((r: any) => {
              const total = r.latency_ms?.total_ms || 0;
              return (
                <div key={r.report_id} className="rounded-2xl border border-ink-700 bg-white p-3.5">
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="chip chip-accent capitalize">{r.input_type}</span>
                      <span className="text-[11px] text-ink-300">{fmtRelative(r.uploaded_at)}</span>
                      {r.model_used && <span className="chip font-mono text-[10px]">{r.model_used}</span>}
                    </div>
                    <div className={"font-mono num text-[15px] " + totalTone(total)}>
                      {total.toFixed(0)} <span className="text-[11px] text-ink-300 font-sans">ms total</span>
                    </div>
                  </div>
                  <StageBar stages={r.latency_ms || {}} total={total} />
                  <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-[11px] font-mono">
                    {Object.entries(r.latency_ms || {}).filter(([k]) => k !== "total_ms").map(([k, v]: any) => (
                      <div key={k} className="rounded-md bg-ink-900/60 px-2 py-1.5 flex justify-between">
                        <span className="text-ink-300">{k}</span>
                        <span className="text-ink-100 num">{Number(v).toFixed(0)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>}
      </Card>
    </div>
  );
}

function Provider({ p, primary }: { p: any; primary?: boolean }) {
  const color = p.provider === "anthropic" ? "bg-warn-soft text-warn-ink"
              : p.provider === "openai"    ? "bg-good-soft text-good-ink"
              : p.provider === "gemini"    ? "bg-info-soft text-info-ink"
              : "bg-ink-800 text-ink-200";
  return (
    <div className="flex items-center gap-2">
      <span className={"chip " + color + " capitalize"}>{p.provider}</span>
      <span className={"font-mono text-[12px] " + (primary ? "text-ink-100" : "text-ink-300")}>{p.model}</span>
    </div>
  );
}

function StageBar({ stages, total }: { stages: Record<string, number>; total: number }) {
  if (!total) return null;
  const order = ["pdf_extract_native_ms","pdf_extract_vision_ms","vision_ocr_ms","transcribe_ms","pii_scrub_ms","llm_first_token_ms","llm_total_ms","persist_ms"];
  const colors: Record<string, string> = {
    pii_scrub_ms: "bg-good",
    pdf_extract_native_ms: "bg-info",
    pdf_extract_vision_ms: "bg-info",
    vision_ocr_ms: "bg-info",
    transcribe_ms: "bg-info",
    llm_first_token_ms: "bg-accent",
    llm_total_ms: "bg-accent-deep",
    persist_ms: "bg-warn",
  };
  return (
    <div className="h-2 w-full rounded-full bg-ink-800 overflow-hidden flex">
      {order.filter(k => stages[k] != null && k !== "total_ms").map(k => {
        const v = stages[k];
        const pct = Math.max(0.5, Math.min(100, (v / total) * 100));
        return <span key={k} title={`${k} · ${v.toFixed(0)} ms`} className={(colors[k] || "bg-ink-300") + " h-full"} style={{ width: `${pct}%` }}/>;
      })}
    </div>
  );
}

function tone(ms: number | undefined, [warnAt, alertAt]: [number, number]): "good"|"warn"|"alert"|"accent" {
  if (ms == null) return "accent";
  if (ms < warnAt) return "good";
  if (ms < alertAt) return "warn";
  return "alert";
}
function totalTone(ms: number) {
  if (ms < 2000) return "text-good-deep";
  if (ms < 3000) return "text-warn-deep";
  return "text-alert-deep";
}
