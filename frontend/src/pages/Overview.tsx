import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Card, StatTile } from "../components/Card";
import { SeverityChip, CategoryDot } from "../components/Severity";
import { fmtRelative } from "../lib/format";

export default function Overview() {
  const { data, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: () => api("/api/overview"),
  });

  if (isLoading) return <Loading />;

  const v = data?.latest_vitals || {};
  const dx = data?.active_diagnoses || [];
  const meds = data?.active_medications || [];
  const suggestions = data?.top_suggestions || [];
  const flags = data?.red_flags || [];

  const noData = dx.length === 0 && meds.length === 0 && Object.keys(v).length === 0;

  return (
    <div className="space-y-7">
      <Header diagnosesCount={dx.length} medsCount={meds.length} />

      {noData && (
        <div className="card card-pad bg-accent-softer/40 border-accent/30">
          <div className="text-[11px] uppercase tracking-[0.18em] text-accent-deep font-semibold">Welcome</div>
          <h3 className="font-display text-[18px] font-semibold text-ink-50 mt-1">Your record is empty.</h3>
          <p className="text-[13.5px] text-ink-200 mt-1.5 leading-relaxed">
            Head to <Link to="/" className="link">Chat</Link> and drop a PDF, photo, or paste a report. Folio will extract it into structure and start building your timeline.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile label="Blood pressure" value={v.bp?.value || "—"}
                   hint={v.bp ? fmtRelative(v.bp.recorded_at) : "no readings"}
                   accent={getBPAccent(v.bp?.value)} />
        <StatTile label="Heart rate" value={v.hr?.value || "—"} hint={v.hr?.unit || "bpm"} accent="accent" />
        <StatTile label="Weight" value={v.weight?.value || "—"} hint={v.weight?.unit || "kg"} accent="info" />
        <StatTile label="BMI" value={v.bmi?.value || "—"}
                   hint={v.bmi ? bmiCategory(v.bmi.value) : "—"}
                   accent={getBMIAccent(v.bmi?.value)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Active diagnoses" eyebrow="Conditions"
              action={<span className="chip">{dx.length}</span>}
              className="lg:col-span-1">
          {dx.length === 0 ? <Empty text="No active diagnoses." />
            : <ul className="divide-y divide-ink-700">
                {dx.map((d: any, i: number) => (
                  <li key={i} className="py-2.5 flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[14px] text-ink-100 capitalize font-medium">{d.condition}</div>
                      <div className="text-[11px] text-ink-300 font-mono mt-0.5">{d.icd10 || "—"} · {d.status}</div>
                    </div>
                    <ConfidenceBar v={d.confidence || 0} />
                  </li>
                ))}
              </ul>}
        </Card>

        <Card title="Current medications" eyebrow="Active regimen"
              action={<span className="chip">{meds.length}</span>}
              className="lg:col-span-1">
          {meds.length === 0 ? <Empty text="No active medications recorded." />
            : <ul className="divide-y divide-ink-700">
                {meds.map((m: any, i: number) => (
                  <li key={i} className="py-2.5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[14px] text-ink-100 capitalize font-medium">{m.display_name || m.name}</div>
                      <span className="chip text-[10px]">{m.dose}</span>
                    </div>
                    <div className="text-[11.5px] text-ink-300 mt-1">{m.frequency} · {m.purpose}</div>
                  </li>
                ))}
              </ul>}
        </Card>

        <Card title="Red flags" eyebrow="Surfacing"
              action={<span className={"chip " + (flags.length ? "chip-alert" : "chip-good")}>{flags.length}</span>}
              className="lg:col-span-1">
          {flags.length === 0 ? <Empty text="Nothing flagged in recent reports." />
            : <ul className="space-y-2.5">
                {flags.map((f: any, i: number) => (
                  <li key={i} className="rounded-xl border border-alert/25 bg-alert-softer p-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="text-sm font-medium text-alert-ink">{f.finding}</div>
                      <SeverityChip s={f.urgency} />
                    </div>
                    <div className="text-[12.5px] text-ink-200">{f.reason}</div>
                  </li>
                ))}
              </ul>}
        </Card>
      </div>

      <Card title="Top suggestions" eyebrow="From the engine"
            action={<Link to="/suggestions" className="text-[12px] link">view all →</Link>}>
        {suggestions.length === 0 ? <Empty text="Run an ingest to populate suggestions." />
          : <ul className="space-y-3">
              {suggestions.map((s: any) => (
                <li key={s.suggestion_id} className="rounded-xl border border-ink-700 bg-ink-900/60 p-4 transition hover:bg-white">
                  <div className="flex items-center gap-2 mb-1.5">
                    <CategoryDot category={s.category} />
                    <div className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">{s.category}</div>
                    <SeverityChip s={s.severity} />
                  </div>
                  <div className="text-[14.5px] font-medium text-ink-50 mb-1">{s.title}</div>
                  <div className="text-[13px] text-ink-200 whitespace-pre-line leading-relaxed">{s.body}</div>
                </li>
              ))}
            </ul>}
      </Card>
    </div>
  );
}

function Header({ diagnosesCount, medsCount }: { diagnosesCount: number; medsCount: number }) {
  return (
    <div className="flex items-end justify-between flex-wrap gap-3">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Health overview</div>
        <h1 className="font-display text-[30px] font-semibold tracking-tight text-ink-50 mt-1">Hello, Rishika.</h1>
        <p className="text-[14px] text-ink-200 mt-1.5 max-w-xl">
          You have <span className="font-semibold text-ink-50">{diagnosesCount}</span> active conditions and{" "}
          <span className="font-semibold text-ink-50">{medsCount}</span> medications on your current regimen.
        </p>
      </div>
      <div className="flex gap-2">
        <Link to="/timeline" className="btn btn-ghost">Timeline</Link>
        <Link to="/ingest" className="btn btn-primary"><span className="text-base leading-none">+</span> New report</Link>
      </div>
    </div>
  );
}

function ConfidenceBar({ v }: { v: number }) {
  const pct = Math.round(v * 100);
  return (
    <div className="text-right">
      <div className="text-[10.5px] text-ink-300 num font-mono">{pct}%</div>
      <div className="mt-1 w-16 h-1 bg-ink-700 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-accent to-accent-deep" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="space-y-4">
      <div className="skel h-12 w-1/3" />
      <div className="grid grid-cols-4 gap-4">{Array.from({length:4}).map((_,i) => <div key={i} className="skel h-24"/>)}</div>
      <div className="grid grid-cols-3 gap-6">{Array.from({length:3}).map((_,i) => <div key={i} className="skel h-48"/>)}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="py-6 text-center text-sm text-ink-300">{text}</div>;
}

function getBPAccent(value?: string): "good"|"warn"|"alert"|"accent" {
  if (!value) return "accent";
  const sys = parseInt(value.split("/")[0], 10);
  if (sys >= 140) return "alert";
  if (sys >= 130) return "warn";
  return "good";
}
function getBMIAccent(v?: string): "good"|"warn"|"alert"|"accent" {
  if (!v) return "accent";
  const n = parseFloat(v);
  if (isNaN(n)) return "accent";
  if (n >= 30) return "alert";
  if (n >= 25 || n < 18.5) return "warn";
  return "good";
}
function bmiCategory(v: string) {
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  if (n < 18.5) return "underweight";
  if (n < 25) return "normal range";
  if (n < 30) return "overweight";
  return "obese";
}
