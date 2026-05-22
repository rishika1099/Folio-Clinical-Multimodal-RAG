import clsx from "clsx";

export function SeverityChip({ s }: { s: string }) {
  const cls =
    s === "action" || s === "critical" || s === "emergent" || s === "urgent" ? "chip-alert"
    : s === "watch" || s === "soon" || s === "high" ? "chip-warn"
    : s === "low" ? "chip-info"
    : s === "normal" || s === "good" ? "chip-good"
    : s === "info" || s === "routine" ? "chip-accent"
    : "";
  return <span className={clsx("chip", cls)}>{s}</span>;
}

export function CategoryDot({ category }: { category: string }) {
  const colors: Record<string, string> = {
    trend:        "bg-accent",
    interaction:  "bg-alert",
    followup:     "bg-warn",
    differential: "bg-info",
    lifestyle:    "bg-good",
    risk:         "bg-alert-deep",
  };
  return <span className={clsx("inline-block h-2 w-2 rounded-full", colors[category] || "bg-ink-400")} />;
}

export function CategoryBadge({ category }: { category: string }) {
  const map: Record<string, string> = {
    trend:        "chip-accent",
    interaction:  "chip-alert",
    followup:     "chip-warn",
    differential: "chip-info",
    lifestyle:    "chip-good",
    risk:         "chip-alert",
  };
  return <span className={clsx("chip", map[category] || "")}>{category}</span>;
}
