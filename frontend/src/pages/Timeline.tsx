import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, ComposedChart, Legend } from "recharts";

import { api } from "../lib/api";
import { Card } from "../components/Card";
import { fmtDate, fmtRelative, clamp } from "../lib/format";

const C = {
  sage:     "#7aaba5",
  sageDeep: "#4f8a83",
  peach:    "#e1a06e",
  peachDeep:"#a36a3f",
  rose:     "#d68888",
  roseDeep: "#a35858",
  lavender: "#9c91c0",
  grid:     "rgba(28,31,42,0.06)",
  axis:     "#aeb2c0",
};

export default function TimelinePage() {
  const reports = useQuery({ queryKey: ["timeline"], queryFn: () => api("/api/timeline") });
  const bp  = useQuery({ queryKey: ["vitals", "bp"], queryFn: () => api("/api/timeline/vitals/bp") });
  const a1c = useQuery({ queryKey: ["labs", "a1c"], queryFn: () => api("/api/timeline/labs/HbA1c") });
  const ldl = useQuery({ queryKey: ["labs", "ldl"], queryFn: () => api("/api/timeline/labs/LDL") });

  const bpData = (bp.data?.points || []).map((p: any) => ({
    t: new Date(p.recorded_at).getTime(),
    sys: parseInt(p.value.split("/")[0], 10) || null,
    dia: parseInt(p.value.split("/")[1], 10) || null,
  }));
  const a1cData = (a1c.data?.points || []).map((p: any) => ({
    t: new Date(p.recorded_at).getTime(), v: parseFloat(p.value),
  }));
  const ldlData = (ldl.data?.points || []).map((p: any) => ({
    t: new Date(p.recorded_at).getTime(), v: parseFloat(p.value),
  }));

  return (
    <div className="space-y-7">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">History</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Timeline</h1>
        <p className="text-sm text-ink-200 mt-1.5">Reports and longitudinal vitals + labs.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="Blood pressure" eyebrow="mmHg"
              action={<Legendly items={[{c: C.sageDeep, l: "systolic"}, {c: C.sage, l: "diastolic"}]} />}>
          <BPSeries data={bpData} />
        </Card>
        <Card title="HbA1c" eyebrow="%">
          <SimpleSeries data={a1cData} color={C.peachDeep} fill={C.peach} unit="%" />
        </Card>
        <Card title="LDL" eyebrow="mg/dL">
          <SimpleSeries data={ldlData} color={C.roseDeep} fill={C.rose} unit="mg/dL" />
        </Card>
      </div>

      <Card title="Reports" eyebrow="Chronological"
            action={<Link to="/ingest" className="btn btn-soft text-[12px] py-1 px-2.5">+ add report</Link>}>
        {!reports.data?.reports?.length ? <div className="text-sm text-ink-300 py-4 text-center">No reports yet.</div>
          : <ol className="relative ml-3 border-l-2 border-ink-700 space-y-4 pl-6">
              {reports.data.reports.map((r: any) => (
                <li key={r.report_id} className="relative">
                  <span className="absolute -left-[33px] top-3 h-3 w-3 rounded-full bg-white border-2 border-accent ring-4 ring-accent-soft" />
                  <Link to={`/reports/${r.report_id}`}
                        className="block rounded-2xl border border-ink-700 bg-white p-4 hover:border-accent/40 hover:shadow-card transition group">
                    <div className="flex items-center gap-3 mb-1.5">
                      <span className="chip chip-accent capitalize">{r.input_type}</span>
                      <span className="text-[11px] text-ink-300 num">{fmtDate(r.uploaded_at)} · {fmtRelative(r.uploaded_at)}</span>
                      <span className="ml-auto text-[11px] text-ink-300 group-hover:text-accent-deep">open →</span>
                    </div>
                    <div className="text-[14px] text-ink-100 font-medium">{clamp(r.raw_summary || "—", 200)}</div>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {r.diagnoses?.length > 0 && <span className="chip chip-accent">{r.diagnoses.length} diagnoses</span>}
                      {r.medications?.length > 0 && <span className="chip">{r.medications.length} meds</span>}
                      {r.labs?.length > 0 && <span className="chip">{r.labs.length} labs</span>}
                      {r.vitals?.length > 0 && <span className="chip">{r.vitals.length} vitals</span>}
                      {r.red_flags?.length > 0 && <span className="chip chip-alert">{r.red_flags.length} flags</span>}
                    </div>
                  </Link>
                </li>
              ))}
            </ol>}
      </Card>
    </div>
  );
}

function BPSeries({ data }: { data: any[] }) {
  if (!data.length) return <Empty />;
  return (
    <div className="h-44 -mx-2">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="sysFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={C.sage} stopOpacity={0.30}/>
              <stop offset="1" stopColor={C.sage} stopOpacity={0.02}/>
            </linearGradient>
          </defs>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString(undefined,{month:"short",day:"numeric"})}
                 tick={{ fontSize: 10, fill: C.axis }} stroke={C.grid} />
          <YAxis tick={{ fontSize: 10, fill: C.axis }} stroke={C.grid} width={36} />
          <Tooltip {...tooltipStyle} formatter={(v: any, n: any) => [`${v} mmHg`, n]} labelFormatter={(t) => new Date(t as number).toLocaleDateString()} />
          <Area type="monotone" dataKey="sys" stroke="none" fill="url(#sysFill)" isAnimationActive={false}/>
          <Line type="monotone" dataKey="sys" stroke={C.sageDeep} strokeWidth={2.2} dot={{ r: 3, fill: C.sageDeep }} activeDot={{ r: 5 }} isAnimationActive={false}/>
          <Line type="monotone" dataKey="dia" stroke={C.sage} strokeWidth={2} strokeDasharray="3 3" dot={{ r: 2.5, fill: C.sage }} isAnimationActive={false}/>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function SimpleSeries({ data, color, fill, unit }: { data: any[]; color: string; fill: string; unit: string }) {
  if (!data.length) return <Empty />;
  return (
    <div className="h-44 -mx-2">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id={`f${color}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={fill} stopOpacity={0.32}/>
              <stop offset="1" stopColor={fill} stopOpacity={0.02}/>
            </linearGradient>
          </defs>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleDateString(undefined,{month:"short",day:"numeric"})}
                 tick={{ fontSize: 10, fill: C.axis }} stroke={C.grid} />
          <YAxis tick={{ fontSize: 10, fill: C.axis }} stroke={C.grid} width={36} />
          <Tooltip {...tooltipStyle}
                   formatter={(v: any) => [`${v} ${unit}`, ""]} labelFormatter={(t) => new Date(t as number).toLocaleDateString()} />
          <Area type="monotone" dataKey="v" stroke="none" fill={`url(#f${color})`} isAnimationActive={false}/>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2.2} dot={{ r: 3, fill: color }} activeDot={{ r: 5 }} isAnimationActive={false}/>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

const tooltipStyle = {
  contentStyle: { background: "#ffffff", border: "1px solid #e0e3eb", borderRadius: 12, fontSize: 12, color: "#272a36", boxShadow: "0 12px 32px -12px rgba(28,31,42,0.14)" },
  labelStyle: { color: "#6b7184", fontSize: 11 },
};

function Empty() { return <div className="h-44 grid place-items-center text-sm text-ink-300">No data yet.</div>; }

function Legendly({ items }: { items: { c: string; l: string }[] }) {
  return (
    <div className="flex items-center gap-3">
      {items.map(i => (
        <span key={i.l} className="flex items-center gap-1.5 text-[11px] text-ink-300">
          <span className="h-1.5 w-3 rounded-full" style={{ background: i.c }} /> {i.l}
        </span>
      ))}
    </div>
  );
}
