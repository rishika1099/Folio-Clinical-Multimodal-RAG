import { useEffect, useState } from "react";
import clsx from "clsx";
import { Card, StatTile } from "../components/Card";

/**
 * Benchmarks page. Fetches the latest eval report from /eval-latest.json
 * (a static file produced by `python -m app.eval.runner --json ...` and
 * committed alongside the frontend) and renders it.
 *
 * The page is intentionally available to authed users only — it sits
 * inside the AuthGuard. The eval data itself doesn't contain PHI.
 */
export default function BenchmarksPage() {
  const [data, setData] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

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

  const e = data.extraction, r = data.rag, c = data.consensus,
        p = data.pii, l = data.latency, ch = data.chat, meta = data.meta;

  return (
    <div className="space-y-7">
      <Header meta={meta} />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile label="Extraction F1" value={fmtPct(e.micro_f1)} hint="micro · all sections" accent="good" />
        <StatTile label="RAG MRR"        value={r.mrr.toFixed(3)} hint={`recall@5 ${fmtPct(rk(r,5))}`} accent="info" />
        <StatTile label="PII recall"     value={fmtPct(p.scrub_recall)} hint={`${meta.n_pii_cases} cases · all classes`} accent="good" />
        <StatTile label="Chat groundedness" value={fmtPct(ch.answer_correctness)} hint={`${ch.n_probes} probes`} accent="accent" />
      </div>

      <Section title="1. Extraction quality" eyebrow="Per-section P/R/F1">
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
          The hash variant is a lower bound — switching to live embeddings typically pushes Recall@5 to 80–90%+.
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
        <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Reproduce</div>
        <h3 className="font-display text-[16px] font-semibold text-ink-50 mt-1">Run the harness yourself</h3>
        <pre className="mt-3 rounded-xl bg-ink-900/60 border border-ink-700 p-3 text-[12px] text-ink-100 overflow-x-auto">
{`docker compose exec backend python -m app.eval.runner
# add --live-embed for real OpenAI embeddings
# add --json eval.json for machine-readable output`}
        </pre>
        <p className="text-[12px] text-ink-300 mt-3 leading-relaxed">
          Gold dataset at <code className="font-mono">backend/app/eval/dataset.py</code>. Hand-authored across 12 medical scenarios spanning text, PDF, image, and voice modalities, with easy/medium/hard difficulty tags and emergency red-flag cases.
        </p>
      </section>
    </div>
  );
}

// ─── helpers ────────────────────────────────────────────────────────────────

function Header({ meta }: { meta: any }) {
  return (
    <div className="flex items-end justify-between flex-wrap gap-3">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Engineering</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Benchmarks</h1>
        <p className="text-sm text-ink-200 mt-1.5 max-w-2xl leading-relaxed">
          25+ metrics across extraction, retrieval, multi-LLM consensus, PII safety, chat groundedness, and latency. Run against a fixed synthetic gold dataset so results are reproducible across runs.
        </p>
      </div>
      <div className="flex items-center gap-2 text-[11px] text-ink-300">
        <span className="chip">{meta.n_extraction_examples} examples</span>
        <span className="chip">{meta.n_rag_queries} RAG queries</span>
        <span className="chip">{meta.n_pii_cases} PII cases</span>
        <span className="chip">{meta.n_chat_probes} chat probes</span>
      </div>
    </div>
  );
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
