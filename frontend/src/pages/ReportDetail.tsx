import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";

import { api, API_BASE } from "../lib/api";
import { Card } from "../components/Card";
import { CategoryDot, SeverityChip } from "../components/Severity";
import { fmtDate } from "../lib/format";

export default function ReportDetailPage() {
  const { id } = useParams();
  const { data, isLoading } = useQuery({
    queryKey: ["report", id],
    queryFn: () => api(`/api/reports/${id}`),
  });

  if (isLoading) return <div className="skel h-48" />;
  if (!data?.report) return <Card><div className="py-10 text-center text-sm text-ink-300">Report not found.</div></Card>;

  const r = data.report;
  return (
    <div className="space-y-7">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <Link to="/timeline" className="text-[12px] link">← back to timeline</Link>
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold mt-2">Report detail</div>
          <h1 className="font-display text-[26px] font-semibold tracking-tight text-ink-50 mt-1">
            {fmtDate(r.uploaded_at)}
          </h1>
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className="chip chip-accent capitalize">{r.input_type}</span>
            {r.model_used && <span className="chip font-mono text-[10.5px]">{r.model_used}</span>}
            <span className="chip font-mono text-[10.5px]">id · {String(r.report_id).slice(0, 8)}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Original input" eyebrow="Source">
          <SourceView r={r} />
        </Card>

        <Card title="Structured extraction" eyebrow="Output">
          <div className="rounded-xl border border-accent/25 bg-accent-softer p-3.5 text-[13px] text-accent-ink leading-relaxed mb-4">
            {r.raw_summary}
          </div>

          <Section title="Diagnoses" rows={r.diagnoses}
            render={(d: any) => <Row title={d.condition} sub={`${d.icd10 || "—"} · ${d.status}`} right={<span className="num font-mono text-accent-deep">{Math.round((d.confidence||0)*100)}%</span>}/>} />
          <Section title="Medications" rows={r.medications}
            render={(m: any) => <Row title={m.name} sub={`${m.dose||""} ${m.frequency||""}`} right={m.purpose}/>} />
          <Section title="Vitals" rows={r.vitals}
            render={(v: any) => <Row title={(v.type || "").toString().toUpperCase()} sub={fmtDate(v.recorded_at)} right={<span className="num font-mono">{v.value} {v.unit||""}</span>}/>} />
          <Section title="Labs" rows={r.labs}
            render={(l: any) => <Row title={l.test} sub={l.reference_range && `ref ${l.reference_range}`}
              right={<span className="flex items-center gap-2 num font-mono">{l.value} {l.unit} <SeverityChip s={l.flag||"normal"}/></span>}/>} />
          <Section title="Symptoms" rows={r.symptoms}
            render={(s: any) => <Row title={s.description} sub={s.onset} right={<SeverityChip s={s.severity||"mild"}/>}/>} />
          <Section title="Red flags" rows={r.red_flags}
            render={(f: any) => <Row title={f.finding} sub={f.reason} right={<SeverityChip s={f.urgency||"routine"}/>}/>} />
        </Card>
      </div>

      {data.consensus && <ConsensusSection meta={data.consensus} />}

      {data.suggestions?.length > 0 && (
        <Card title="Suggestions from this report" eyebrow="Generated cold-path">
          <ul className="space-y-3">
            {data.suggestions.map((s: any) => (
              <li key={s.suggestion_id} className="rounded-xl border border-ink-700 bg-white p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <CategoryDot category={s.category}/>
                  <span className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">{s.category}</span>
                  <SeverityChip s={s.severity}/>
                </div>
                <div className="text-[14.5px] font-semibold text-ink-50">{s.title}</div>
                <div className="text-[13px] text-ink-200 mt-1 whitespace-pre-line leading-relaxed">{s.body}</div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {r.latency_ms && Object.keys(r.latency_ms).length > 0 && <Card title="Latency breakdown" eyebrow="Per stage">
        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {Object.entries(r.latency_ms).map(([k, v]: any) => (
            <li key={k} className="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
              <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-mono font-semibold">{k}</div>
              <div className="text-[15px] text-accent-deep num font-mono mt-0.5">{Number(v).toFixed(0)} ms</div>
            </li>
          ))}
        </ul>
      </Card>}
    </div>
  );
}

function SourceView({ r }: { r: any }) {
  const hasAttachment = !!r.attachment_id;
  const isImage = (r.attachment_mime || "").startsWith("image/");
  const isPdf = r.attachment_mime === "application/pdf";

  if (hasAttachment) {
    const url = `${API_BASE}/api/reports/${r.report_id}/attachment`;
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 rounded-xl border border-ink-700 bg-ink-900/60 px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <FileIcon mime={r.attachment_mime}/>
            <div className="min-w-0">
              <div className="text-[14px] font-medium text-ink-100 truncate">{r.attachment_filename}</div>
              <div className="text-[11px] text-ink-300 font-mono num">
                {r.attachment_mime} · {prettyBytes(r.attachment_size)}
              </div>
            </div>
          </div>
          <a href={`${url}?inline=false`} download={r.attachment_filename} className="btn btn-soft text-[12px] py-1.5 px-2.5">Download</a>
        </div>

        {isImage && (
          <img src={url} alt={r.attachment_filename}
               className="w-full rounded-xl border border-ink-700 bg-white" />
        )}
        {isPdf && (
          <object data={url} type="application/pdf" className="w-full h-[600px] rounded-xl border border-ink-700 bg-white">
            <div className="p-8 text-center text-sm text-ink-300">
              Your browser can't preview PDFs inline.
              <a href={`${url}?inline=false`} className="link ml-1">Download instead</a>.
            </div>
          </object>
        )}

        {r.source_text && (
          <details className="rounded-xl border border-ink-700 bg-white px-3 py-2">
            <summary className="text-[12px] text-ink-300 cursor-pointer">Show extracted text (raw)</summary>
            <pre className="mt-2 whitespace-pre-wrap text-[12px] text-ink-200 leading-relaxed">{r.source_text}</pre>
          </details>
        )}
      </div>
    );
  }

  return r.source_text
    ? <pre className="whitespace-pre-wrap text-[13px] text-ink-100 leading-relaxed font-sans">{r.source_text}</pre>
    : <div className="text-sm text-ink-300">No source content saved.</div>;
}

function FileIcon({ mime }: { mime?: string }) {
  const isImg = (mime || "").startsWith("image/");
  return (
    <div className={clsx("h-10 w-10 grid place-items-center rounded-lg shrink-0",
      isImg ? "bg-info-soft text-info-deep" : "bg-warn-soft text-warn-deep")}>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7">
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" strokeLinejoin="round"/>
        <path d="M14 3v5h5" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function ConsensusSection({ meta }: { meta: any }) {
  const fields: [string, any[]][] = Object.entries(meta.fields || {});
  return (
    <Card title="Consensus run" eyebrow={`${Math.round((meta.overall_agreement||0)*100)}% agreement across ${meta.n_models} models`}>
      <div className="space-y-3">
        {fields.filter(([_, c]) => c.length > 0).map(([field, clusters]) => (
          <div key={field}>
            <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold mb-1.5">{field}</div>
            <div className="space-y-1">
              {clusters.map((c: any, i: number) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="text-[12.5px] text-ink-100 flex-1 truncate font-mono">{c.value_key}</div>
                  <div className="flex items-center gap-1">
                    {(["anthropic","openai","gemini"] as const).map(p => (
                      <span key={p} title={p} className={clsx("h-2 w-2 rounded-full",
                        c.providers?.includes(p) ? providerColor(p) : "bg-ink-700")}/>
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
    </Card>
  );
}

function providerColor(p: string) {
  return p === "anthropic" ? "bg-warn-deep"
       : p === "openai"    ? "bg-good-deep"
       : p === "gemini"    ? "bg-info-deep"
       : "bg-ink-300";
}

function Section({ title, rows, render }: { title: string; rows: any[]; render: (r: any) => React.ReactNode }) {
  if (!rows?.length) return null;
  return (
    <div className="mb-4">
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold mb-1.5">{title}</div>
      <div className="divide-y divide-ink-700">{rows.map((r, i) => <div key={i}>{render(r)}</div>)}</div>
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

function prettyBytes(n?: number) {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n/1024).toFixed(1)} KB`;
  return `${(n/1024/1024).toFixed(1)} MB`;
}
