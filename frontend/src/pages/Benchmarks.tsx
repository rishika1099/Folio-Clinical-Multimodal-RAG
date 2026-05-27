import { useEffect, useState } from "react";
import clsx from "clsx";
import { Card, StatTile } from "../components/Card";

type ModelKey = "haiku" | "sonnet";

/**
 * Benchmarks page. Fetches /eval-latest.json (built by
 * `python -m app.eval.compare`). The new schema has a `models` key with
 * one entry per LLM scored; the page lets you toggle between them and
 * shows the model-independent sections (RAG, PII, consensus, latency,
 * chat) once below.
 *
 * Backwards-compatible with the old single-model schema (data.extraction
 * at the top level) so an older eval-latest.json still renders.
 */
export default function BenchmarksPage() {
  const [data, setData] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [model, setModel] = useState<ModelKey>("haiku");

  useEffect(() => {
    fetch("/eval-latest.json")
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setData)
      .catch(e => setErr(e.message || "Failed to load benchmark report"));
  }, []);

  if (err) return (
    <Card><div className="py-6 text-center text-sm text-alert-deep">Couldn't load report: {err}</div></Card>
  );
  if (!data) return <div className="skel h-32" />;

  const comparison = !!data.models;
  const e = comparison ? data.models[model].extraction : data.extraction;
  const source = comparison ? data.models[model].source : null;
  const r = data.rag, c = data.consensus, p = data.pii, l = data.latency, ch = data.chat, meta = data.meta;

  return (
    <div className="space-y-7">
      <Header meta={meta} comparison={comparison} />

      {comparison && (
        <ModelToggle models={data.models} current={model} onChange={setModel} />
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label={`${labelOf(data, model)} F1`} value={fmtPct(e.micro_f1)} hint="micro · all sections" accent="good" />
        <StatTile label="RAG MRR"        value={r.mrr.toFixed(3)} hint={`recall@5 ${fmtPct(rk(r,5))}`} accent="info" />
        <StatTile label="PII recall"     value={fmtPct(p.scrub_recall)} hint={`${meta.n_pii_cases} cases · all classes`} accent="good" />
        <StatTile label="Chat groundedness" value={fmtPct(ch.answer_correctness)} hint={`${ch.n_probes} probes`} accent="accent" />
      </div>

      <Section title={`1. Extraction quality — ${labelOf(data, model)}`} eyebrow="Per-section P/R/F1">
        {source && <SourceStrip source={source} model={model} />}
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold">
              <th className="text-left py-2 px-2">Section</th>
              <th className="text-right py-2 px-2">TP</th>
              <th className="text-right py-2 px-2">FP</th>
              <th className="text-right py-2 px-2">FN</th>
              <th className="text-right py-2 px-2">Precision</th>
              <th className="text-right py-2 px-2">Recall</th>
              <th className="text-right py-2 px-2">F1</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-700">
            {Object.entries<any>(e.per_section).map(([sec, s]: any) => {
              const prec = (s.tp + s.fp) ? s.tp / (s.tp + s.fp) : 1;
              const rec  = (s.tp + s.fn) ? s.tp / (s.tp + s.fn) : 1;
              const f1   = (prec + rec) ? 2 * prec * rec / (prec + rec) : 0;
              return (
                <tr key={sec} className="text-[13px]">
                  <td className="py-2 px-2 text-ink-100 capitalize">{sec.replace("_", " ")}</td>
                  <td className="py-2 px-2 text-right num font-mono">{s.tp}</td>
                  <td className="py-2 px-2 text-right num font-mono">{s.fp}</td>
                  <td className="py-2 px-2 text-right num font-mono">{s.fn}</td>
                  <td className="py-2 px-2 text-right num font-mono">{fmtPct(prec)}</td>
                  <td className="py-2 px-2 text-right num font-mono">{fmtPct(rec)}</td>
                  <td className="py-2 px-2 text-right num font-mono font-semibold text-accent-deep">{fmtPct(f1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
          <Mini label="Schema validity"   value={fmtPct(e.schema_valid)} tone={tone(e.schema_valid, 0.95, 0.8)} />
          <Mini label="Hallucination"     value={fmtPct(e.hallucination)} tone={tone(1 - e.hallucination, 0.97, 0.9)} />
          <Mini label="Coverage of gold"  value={fmtPct(e.coverage)} tone={tone(e.coverage, 0.9, 0.7)} />
          <Mini label="Macro F1"          value={fmtPct(e.macro_f1)} tone="good" />
        </div>
        <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
          <SubTable title="By modality" rows={Object.entries<any>(e.by_modality)
            .map(([k, v]: any) => ({ key: k, n: v.n, val: fmtPct(v.macro_f1) }))} />
          <SubTable title="By difficulty" rows={Object.entries<any>(e.by_difficulty)
            .map(([k, v]: any) => ({ key: k, n: v.n, val: fmtPct(v.macro_f1) }))} />
        </div>
      </Section>

      {comparison && (
        <Section title="Head-to-head" eyebrow="Same gold set, two models">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold">
                <th className="text-left py-2 px-2">Metric</th>
                <th className="text-right py-2 px-2">{data.models.haiku.label}</th>
                <th className="text-right py-2 px-2">{data.models.sonnet.label}</th>
                <th className="text-right py-2 px-2">Δ (Sonnet − Haiku)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700">
              {([
                ["Micro-F1", "micro_f1", true],
                ["Macro-F1", "macro_f1", true],
                ["Coverage", "coverage", true],
                ["Schema validity", "schema_valid", true],
                ["Hallucination (lower better)", "hallucination", false],
              ] as [string, string, boolean][]).map(([label, key, higherIsBetter]) => {
                const a = data.models.haiku.extraction[key];
                const b = data.models.sonnet.extraction[key];
                const delta = b - a;
                const positive = higherIsBetter ? delta > 0 : delta < 0;
                return (
                  <tr key={key} className="text-[13px]">
                    <td className="py-2 px-2 text-ink-100">{label}</td>
                    <td className="py-2 px-2 text-right num font-mono">{fmtPct(a)}</td>
                    <td className="py-2 px-2 text-right num font-mono">{fmtPct(b)}</td>
                    <td className={clsx("py-2 px-2 text-right num font-mono font-semibold",
                          Math.abs(delta) < 0.001 ? "text-ink-300"
                          : positive ? "text-good-deep" : "text-alert-deep")}>
                      {delta > 0 ? "+" : ""}{(delta * 100).toFixed(1)} pts
                    </td>
                  </tr>
                );
              })}
              {/* Cost row */}
              <CostRow data={data} />
            </tbody>
          </table>
          <p className="text-[12px] text-ink-300 mt-4 leading-relaxed">
            Both models were scored against the same 30-example gold set using the identical prompt and scorer.
            Sonnet's input tokens cost 3× Haiku and output 3× as well — so a Sonnet pass is ~3× the dollar amount for a marginal F1 lift.
            That's why Folio routes the hot path through Haiku and reserves Sonnet for the High-confidence multi-LLM consensus mode.
          </p>
        </Section>
      )}

      <Section title="2. RAG retrieval" eyebrow="Information retrieval">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          {[1,3,5,10].map(k => (
            <Mini key={k} label={`Recall@${k}`} value={fmtPct(rk(r, k))} tone={tone(rk(r, k), 0.7, 0.4)} />
          ))}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Mini label="MRR"             value={r.mrr.toFixed(3)} tone="info" />
          <Mini label="NDCG@10"         value={r.ndcg10.toFixed(3)} tone="info" />
          <Mini label="Embed time / q"  value={`${r.mean_embed_ms.toFixed(2)} ms`} />
          <Mini label="Search time / q" value={`${r.mean_search_ms.toFixed(3)} ms`} />
        </div>
        <p className="text-[12px] text-ink-300 mt-4">
          Embeddings: <span className="font-mono">{meta.live_embed ? "OpenAI text-embedding-3-small (live)" : "deterministic hash bag (no network)"}</span>.
        </p>
      </Section>

      <Section title="3. Multi-LLM consensus" eyebrow="3-model ensemble">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <Mini label="Unanimous (3/3)" value={fmtPct(c.unanimous_rate)} tone="info" />
          <Mini label="Convergence (≥2/3)" value={fmtPct(c.convergence_rate)} tone="good" />
          <Mini label="Cluster correctness" value={fmtPct(c.cluster_correctness)} tone={tone(c.cluster_correctness, 0.95, 0.8)} />
          <Mini label="Recall lift" value={`+${fmtPct(c.high_conf_recall_lift)}`} tone="accent" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Mini label="Mean single-model recall" value={fmtPct(c.mean_single_recall)} />
          <Mini label="Consensus recall" value={fmtPct(c.consensus_recall)} tone="accent" />
          <Mini label="Cost ratio (vs single)" value={`${c.cost_ratio.toFixed(1)}×`} tone="warn" />
        </div>
      </Section>

      <Section title="4. PII scrubbing" eyebrow="Privacy guarantees">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
          <Mini label="Scrub recall"        value={fmtPct(p.scrub_recall)} tone={tone(p.scrub_recall, 0.99, 0.9)} />
          <Mini label="Content preservation" value={fmtPct(p.content_preservation)} tone={tone(p.content_preservation, 0.99, 0.9)} />
          <Mini label="Classes covered"     value={Object.keys(p.by_class).length.toString()} />
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold">
              <th className="text-left py-2 px-2">Class</th>
              <th className="text-right py-2 px-2">Cases</th>
              <th className="text-right py-2 px-2">Recall</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-700">
            {Object.entries<any>(p.by_class).map(([cls, v]: any) => (
              <tr key={cls} className="text-[13px]">
                <td className="py-2 px-2 text-ink-100">{cls}</td>
                <td className="py-2 px-2 text-right num font-mono">{v.total}</td>
                <td className="py-2 px-2 text-right num font-mono text-good-deep">{fmtPct(v.recall)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="5. Chat groundedness" eyebrow="Truthfulness checks">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Mini label="Answer correctness"    value={fmtPct(ch.answer_correctness)} tone="good" />
          <Mini label="Citation correctness"  value={fmtPct(ch.citation_correctness)} tone="good" />
          <Mini label="Red-flag escalation"   value={fmtPct(ch.red_flag_recall)} tone="alert" />
          <Mini label="Hallucination guard"   value={fmtPct(ch.hallucination_guard)} tone="good" />
        </div>
      </Section>

      <Section title="6. Latency" eyebrow="Per-stage distribution">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold">
              <th className="text-left py-2 px-2">Stage</th>
              <th className="text-right py-2 px-2">p50</th>
              <th className="text-right py-2 px-2">p95</th>
              <th className="text-right py-2 px-2">p99</th>
              <th className="text-right py-2 px-2">Samples</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-700">
            {[
              { label: "PII scrub",         d: l.pii_scrub },
              { label: "Hash embed (1 doc)", d: l.hash_embed },
              { label: "Cosine search (full corpus)", d: l.cosine_search },
            ].map(row => {
              const s = (row.d.samples || []).slice().sort((a:number,b:number)=>a-b);
              const pct = (q:number) => s.length ? s[Math.min(s.length-1, Math.floor(q*(s.length-1)))] : 0;
              return (
                <tr key={row.label} className="text-[13px]">
                  <td className="py-2 px-2 text-ink-100">{row.label}</td>
                  <td className="py-2 px-2 text-right num font-mono">{pct(0.5).toFixed(3)} ms</td>
                  <td className="py-2 px-2 text-right num font-mono">{pct(0.95).toFixed(3)} ms</td>
                  <td className="py-2 px-2 text-right num font-mono">{pct(0.99).toFixed(3)} ms</td>
                  <td className="py-2 px-2 text-right num font-mono text-ink-300">{s.length}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>

      <section className="card card-pad">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="max-w-xl">
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Methodology</div>
            <h3 className="font-display text-[16px] font-semibold text-ink-50 mt-1">Gold dataset + open source</h3>
            <p className="text-[13px] text-ink-200 mt-2 leading-relaxed">
              All numbers above are scored against a hand-authored gold set: {meta.n_extraction_examples} medical scenarios across text, PDF, image, and voice inputs, tagged for difficulty and including emergency red-flag cases. The harness is reproducible — every metric here regenerates from the same Python module.
            </p>
          </div>
          <a href="https://github.com/rishika1099/Folio-Clinical-Multimodal-RAG/blob/main/EVAL_REPORT.md"
             target="_blank" rel="noreferrer"
             className="btn btn-ghost text-[12.5px] py-2 px-3 shrink-0">
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            View report on GitHub
          </a>
        </div>
      </section>
    </div>
  );
}

// ─── helpers ────────────────────────────────────────────────────────────────

function Header({ meta, comparison }: { meta: any; comparison: boolean }) {
  return (
    <div className="flex items-end justify-between flex-wrap gap-3">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Engineering</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Benchmarks</h1>
        <p className="text-sm text-ink-200 mt-1.5 max-w-2xl leading-relaxed">
          25+ metrics across extraction, retrieval, multi-LLM consensus, PII safety, chat groundedness, and latency. {comparison && "Head-to-head between two production-tier Anthropic models on the same gold set."} Reproducible — same scorer, same data, same seed.
        </p>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-ink-300 flex-wrap">
        <span className="chip">{meta.n_extraction_examples} examples</span>
        <span className="chip">{meta.n_rag_queries} RAG queries</span>
        <span className="chip">{meta.n_pii_cases} PII cases</span>
        <span className="chip">{meta.n_chat_probes} chat probes</span>
      </div>
    </div>
  );
}

function ModelToggle({ models, current, onChange }: {
  models: Record<string, { label: string; source: any; extraction: any }>;
  current: ModelKey;
  onChange: (m: ModelKey) => void;
}) {
  const keys = Object.keys(models) as ModelKey[];
  return (
    <div className="card card-pad">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Model</div>
          <div className="text-[13px] text-ink-200 mt-0.5">Toggle between models. Per-section table updates; shared metrics below stay the same.</div>
        </div>
        <div className="flex gap-1.5">
          {keys.map(k => {
            const active = k === current;
            const m = models[k];
            return (
              <button key={k} onClick={() => onChange(k)}
                      className={clsx(
                        "px-3.5 py-2 rounded-xl text-[12.5px] font-medium transition border",
                        active
                          ? "bg-accent text-white border-accent shadow-glow"
                          : "bg-white border-ink-700 text-ink-100 hover:border-accent/40"
                      )}>
                {m.label}
                <span className={clsx("ml-2 font-mono num text-[10.5px]",
                  active ? "text-white/80" : "text-ink-300")}>
                  F1 {(m.extraction.micro_f1 * 100).toFixed(1)}%
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SourceStrip({ source, model }: { source: any; model: ModelKey }) {
  // Anthropic list prices (approximate): Haiku 4.5 $1/$5 per Mtok, Sonnet 4.5 $3/$15.
  const inRate  = model === "haiku" ? 1.0 : 3.0;
  const outRate = model === "haiku" ? 5.0 : 15.0;
  const cost = ((source.total_input_tokens || 0) / 1e6) * inRate
             + ((source.total_output_tokens || 0) / 1e6) * outRate;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5 text-[11px]">
      <span className="chip font-mono">{source.model}</span>
      <span className="chip">{source.n} examples</span>
      <span className="chip font-mono num">{source.total_input_tokens?.toLocaleString()} in / {source.total_output_tokens?.toLocaleString()} out</span>
      <span className="chip font-mono num">${cost.toFixed(4)}</span>
    </div>
  );
}

function CostRow({ data }: { data: any }) {
  const cost = (label: ModelKey, inRate: number, outRate: number) => {
    const s = data.models[label].source;
    return ((s.total_input_tokens || 0) / 1e6) * inRate
         + ((s.total_output_tokens || 0) / 1e6) * outRate;
  };
  const haikuCost  = cost("haiku",  1.0,  5.0);
  const sonnetCost = cost("sonnet", 3.0, 15.0);
  const ratio = sonnetCost / Math.max(haikuCost, 1e-9);
  return (
    <tr className="text-[13px]">
      <td className="py-2 px-2 text-ink-100">Cost per pass (USD)</td>
      <td className="py-2 px-2 text-right num font-mono">${haikuCost.toFixed(4)}</td>
      <td className="py-2 px-2 text-right num font-mono">${sonnetCost.toFixed(4)}</td>
      <td className="py-2 px-2 text-right num font-mono font-semibold text-warn-deep">{ratio.toFixed(1)}×</td>
    </tr>
  );
}

function labelOf(data: any, model: ModelKey): string {
  return data.models?.[model]?.label || "Live model";
}

function Section({ title, eyebrow, children }: { title: string; eyebrow?: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <header className="px-5 pt-4 pb-3 border-b border-ink-700">
        {eyebrow && <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300 mb-0.5">{eyebrow}</div>}
        <h2 className="font-display text-[15px] font-semibold tracking-tight text-ink-50">{title}</h2>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Mini({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "alert" | "accent" | "info" }) {
  const tcl = {
    good:   "text-good-deep",
    warn:   "text-warn-deep",
    alert:  "text-alert-deep",
    info:   "text-info-deep",
    accent: "text-accent-deep",
  }[tone || "accent"];
  return (
    <div className="rounded-xl border border-ink-700 bg-white px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-[0.14em] text-ink-300">{label}</div>
      <div className={clsx("mt-1 font-display text-[18px] font-semibold num", tcl)}>{value}</div>
    </div>
  );
}

function SubTable({ title, rows }: { title: string; rows: { key: string; n: number; val: string }[] }) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/40 p-3">
      <div className="text-[10.5px] uppercase tracking-[0.14em] text-ink-300 font-semibold mb-2">{title}</div>
      <ul className="space-y-1">
        {rows.map(r => (
          <li key={r.key} className="flex items-center justify-between text-[12.5px]">
            <span className="text-ink-100 capitalize">{r.key}</span>
            <span className="text-ink-300 font-mono num">n={r.n}</span>
            <span className="text-accent-deep font-mono num">{r.val}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function fmtPct(x: number): string {
  if (x == null || isNaN(x)) return "—";
  return `${(x * 100).toFixed(1)}%`;
}

function rk(r: any, k: number): number {
  const rec = r.recall_at;
  return rec[k] ?? rec[String(k)] ?? 0;
}

function tone(v: number, good: number, warn: number): "good"|"warn"|"alert" {
  if (v >= good) return "good";
  if (v >= warn) return "warn";
  return "alert";
}
