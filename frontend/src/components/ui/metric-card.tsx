import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";

import { SpotlightCard } from "@/components/godui/spotlight-card";
import { cn } from "@/lib/cn";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  caption?: string;
  footer?: ReactNode;
  className?: string;
  href?: string;
  unit?: string;
  tone?: "neutral" | "accent" | "critical" | "warn" | "ok";
  onClick?: () => void;
  active?: boolean;
  size?: "default" | "compact";
}

/** A single figure with the context needed to read it correctly. */
export function MetricCard({ label, value, caption, footer, className, href, unit, tone = "neutral", onClick, active = false, size = "default" }: MetricCardProps): JSX.Element {
  const colors = { neutral: "text-ink", accent: "text-accent", critical: "text-critical", warn: "text-warn", ok: "text-ok" };
  const interactive = Boolean(href || onClick);
  // Units are written as plurals ("projects"); a single item reads "1 project".
  const shownUnit = unit && value === 1 && /^[a-z]+s$/.test(unit) ? unit.slice(0, -1) : unit;
  const content = <>
      <span className="workspace-metric-label font-medium">{label}{interactive ? <span className="workspace-metric-affordance" aria-hidden="true"><ArrowUpRight size={14} /></span> : null}</span>{" "}
      <span className={cn("workspace-metric-value", colors[tone])} data-numeric>
        {value}{shownUnit ? <>{" "}<span className="ml-1.5 text-meta font-normal text-ink-secondary">{shownUnit}</span></> : null}
      </span>{" "}
      {caption ? <span className="workspace-metric-caption">{caption}</span> : null}
    </>;
  return <SpotlightCard contain={false} wrapContent={false} border={false} radius={260}
    glowColor="color-mix(in srgb, var(--metric-tone) 8%, transparent)"
    className={cn("workspace-metric flex flex-col border border-line", className)} data-tone={tone} data-size={size}
    data-active={active || undefined} data-interactive={interactive || undefined}>
    {href ? <Link to={href} className="workspace-metric-body">{content}</Link>
      : onClick ? <button type="button" onClick={onClick} aria-pressed={active} className="workspace-metric-body">{content}</button>
        : <div className="workspace-metric-body">{content}</div>}
    {footer ? <div className="relative z-10 border-t border-line px-5 py-3">{footer}</div> : null}
  </SpotlightCard>;
}
