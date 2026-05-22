import clsx from "clsx";

export function Card({ title, action, className, children, eyebrow }: {
  title?: React.ReactNode;
  eyebrow?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={clsx("card", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-ink-700">
          <div>
            {eyebrow && <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300 mb-0.5">{eyebrow}</div>}
            <h3 className="font-display text-[14px] font-semibold tracking-tight text-ink-50">{title}</h3>
          </div>
          {action}
        </header>
      )}
      <div className="card-pad">{children}</div>
    </section>
  );
}

export function StatTile({ label, value, hint, accent }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode;
  accent?: "good" | "warn" | "alert" | "accent" | "info";
}) {
  const tone = {
    good:   { bar: "from-good to-good-deep",     text: "text-good-deep" },
    warn:   { bar: "from-warn to-warn-deep",     text: "text-warn-deep" },
    alert:  { bar: "from-alert to-alert-deep",   text: "text-alert-deep" },
    accent: { bar: "from-accent to-accent-deep", text: "text-accent-deep" },
    info:   { bar: "from-info to-info-deep",     text: "text-info-deep" },
  }[accent || "accent"];
  return (
    <div className="card card-pad relative overflow-hidden">
      <div className={clsx("absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b", tone.bar)} />
      <div className="text-[10.5px] uppercase tracking-[0.18em] text-ink-300 font-semibold">{label}</div>
      <div className={clsx("mt-1.5 font-display text-[28px] font-semibold tracking-tight num", tone.text)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-300">{hint}</div>}
    </div>
  );
}
