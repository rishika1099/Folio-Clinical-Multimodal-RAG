import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";

import { api } from "../lib/api";
import { Card } from "../components/Card";
import { CategoryDot, SeverityChip } from "../components/Severity";
import { fmtRelative } from "../lib/format";

const CATEGORIES = ["all", "trend", "interaction", "followup", "differential", "lifestyle", "risk"] as const;
const SEVERITIES = ["any", "info", "watch", "action"] as const;

export default function SuggestionsPage() {
  const [cat, setCat] = useState<typeof CATEGORIES[number]>("all");
  const [sev, setSev] = useState<typeof SEVERITIES[number]>("any");
  const qc = useQueryClient();

  const params = new URLSearchParams();
  if (cat !== "all") params.set("category", cat);
  if (sev !== "any") params.set("severity", sev);

  const { data, isLoading } = useQuery({
    queryKey: ["suggestions", cat, sev],
    queryFn: () => api(`/api/suggestions?${params.toString()}`),
  });

  const dismiss = useMutation({
    mutationFn: (id: string) => api(`/api/suggestions/${id}/dismiss`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["suggestions"] }),
  });

  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    (data?.suggestions || []).forEach((s: any) => { m[s.category] = (m[s.category] || 0) + 1; });
    return m;
  }, [data]);
  const total = data?.suggestions?.length || 0;

  return (
    <div className="space-y-7">
      <div>
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-semibold">Insights</div>
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink-50 mt-1">Suggestions</h1>
        <p className="text-sm text-ink-200 mt-1.5">All findings, ranked by severity. Dismiss anything that isn't useful — your dismissals shape future ranking.</p>
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-5">
          <Filter label="Category" options={CATEGORIES as any} value={cat} onChange={setCat as any} counts={cat === "all" ? counts : undefined} />
          <Filter label="Severity" options={SEVERITIES as any} value={sev} onChange={setSev as any} />
          <div className="ml-auto text-[11.5px] text-ink-300 font-mono num">{total} result{total === 1 ? "" : "s"}</div>
        </div>
      </Card>

      {isLoading ? <div className="skel h-32"/> :
        !data?.suggestions?.length ? <Card><div className="py-10 text-center"><div className="mx-auto h-10 w-10 rounded-full bg-good-soft text-good-deep grid place-items-center mb-3">✓</div><div className="text-[14px] text-ink-100 font-medium">All clear</div><div className="text-sm text-ink-300 mt-1">No suggestions match these filters.</div></div></Card> :
        <div className="space-y-3">
          {data.suggestions.map((s: any) => (
            <SuggestionRow key={s.suggestion_id} s={s} onDismiss={() => dismiss.mutate(s.suggestion_id)} />
          ))}
        </div>}
    </div>
  );
}

function SuggestionRow({ s, onDismiss }: { s: any; onDismiss: () => void }) {
  const tone = sevTone(s.severity);
  return (
    <div className={clsx("card card-pad relative overflow-hidden")}>
      <div className={clsx("absolute left-0 top-0 bottom-0 w-1", tone.bar)} />
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <CategoryDot category={s.category} />
            <span className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">{s.category}</span>
            <SeverityChip s={s.severity} />
            <span className="text-[11px] text-ink-300">· {fmtRelative(s.created_at)}</span>
          </div>
          <div className="text-[15.5px] font-semibold text-ink-50 mb-1.5 tracking-tight">{s.title}</div>
          <div className="text-[13.5px] text-ink-200 whitespace-pre-line leading-relaxed">{s.body}</div>
          {s.evidence?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {s.evidence.map((e: string, i: number) => <span key={i} className="chip text-[10px] font-mono">{e}</span>)}
            </div>
          )}
        </div>
        <button onClick={onDismiss} className="btn btn-ghost text-[12px] py-1.5 px-2.5">Dismiss</button>
      </div>
    </div>
  );
}

function sevTone(s: string) {
  if (s === "action") return { bar: "bg-gradient-to-b from-alert to-alert-deep" };
  if (s === "watch")  return { bar: "bg-gradient-to-b from-warn to-warn-deep" };
  return { bar: "bg-gradient-to-b from-accent to-accent-deep" };
}

function Filter<T extends string>({ label, options, value, onChange, counts }: {
  label: string; options: readonly T[]; value: T; onChange: (v: T) => void; counts?: Record<string, number>;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[10.5px] uppercase tracking-[0.16em] text-ink-300 font-semibold">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map(o => (
          <button key={o} onClick={() => onChange(o)}
            className={clsx("chip cursor-pointer transition", value === o && "chip-accent")}>
            {o}
            {counts && counts[o] ? <span className="ml-1 text-[10px] font-mono num text-ink-300">·{counts[o]}</span> : null}
          </button>
        ))}
      </div>
    </div>
  );
}
