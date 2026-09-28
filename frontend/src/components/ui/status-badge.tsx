import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleDot,
  Info,
  MinusCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import { displayTerm } from "@/lib/terminology";

export type Tone = "ok" | "warn" | "critical" | "advisory" | "accent" | "neutral";

const TONES: Record<Tone, string> = {
  ok: "bg-ok-tint text-ok border-ok/25",
  warn: "bg-warn-tint text-warn border-warn/25",
  critical: "bg-critical-tint text-critical border-critical/25",
  advisory: "bg-advisory-tint text-advisory border-advisory/25",
  accent: "bg-accent-tint text-accent border-accent/25",
  neutral: "bg-muted-tint text-ink-secondary border-line",
};

/** Each tone carries a distinct glyph, so meaning survives without colour perception. */
const ICONS: Record<Tone, LucideIcon> = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  critical: CircleAlert,
  advisory: Info,
  accent: CircleDot,
  neutral: MinusCircle,
};

export function healthTone(band: string): Tone {
  const value = band.toLowerCase();
  if (value === "green") return "ok";
  if (value === "amber") return "warn";
  if (value === "red") return "critical";
  return "neutral";
}

export function confidenceTone(band: string): Tone {
  const value = band.toLowerCase();
  if (value === "high") return "ok";
  if (value === "medium") return "warn";
  if (value === "low") return "critical";
  return "neutral";
}

export function severityTone(severity: string): Tone {
  const value = severity.toLowerCase();
  if (value === "critical") return "critical";
  if (value === "high") return "advisory";
  if (value === "medium") return "warn";
  if (value === "low") return "accent";
  return "neutral";
}

export function traceTone(status: string): Tone {
  const value = status.trim().toLowerCase();
  if (value === "verified" || value === "covered") return "ok";
  if (["not verified", "no linked test case", "missing", "uncovered"].includes(value)) return "critical";
  if (["test not run", "partial", "pending", "suspect", "incomplete"].includes(value)) return "warn";
  return "neutral";
}

/** Workflow wording varies by record type, so the shared vocabulary is mapped once. */
export function statusTone(status: string): Tone {
  const value = status.toLowerCase();
  if (["complete", "completed", "closed", "resolved", "passed", "approved", "verified", "done", "mitigated"].includes(value)) {
    return "ok";
  }
  if (["at risk", "blocked", "overdue", "rejected", "failed", "not ready", "escalated"].includes(value)) {
    return "critical";
  }
  // A newly raised record is work to do, not a failure, so "Open" is not shown as an alarm.
  if (["open", "not started", "not assessed", "not run"].includes(value)) return "accent";
  if (["in progress", "in review", "pending", "under review", "ready for review", "preparing", "passed with conditions", "approved with conditions", "proposed", "monitoring"].includes(value)) {
    return "warn";
  }
  return "neutral";
}

interface StatusBadgeProps {
  label: string;
  tone?: Tone;
  showIcon?: boolean;
  className?: string;
}

export function StatusBadge({
  label,
  tone = "neutral",
  showIcon = true,
  className,
}: StatusBadgeProps): JSX.Element {
  const Icon = ICONS[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-meta font-medium",
        TONES[tone],
        className,
      )}
    >
      {showIcon ? <Icon aria-hidden="true" className="h-3 w-3 shrink-0" /> : null}
      {displayTerm(label)}
    </span>
  );
}
