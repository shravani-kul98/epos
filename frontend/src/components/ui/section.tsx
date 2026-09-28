import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { MetricCard } from "@/components/ui/metric-card";
import { cn } from "@/lib/cn";

interface SectionProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  /** Accent applied to the icon, tying a section to its domain colour. */
  accent?: "accent" | "teal" | "purple" | "indigo" | "cyan" | "warn" | "critical";
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

const ACCENTS: Record<NonNullable<SectionProps["accent"]>, string> = {
  accent: "bg-accent-tint text-accent",
  teal: "bg-teal-tint text-teal",
  purple: "bg-purple-tint text-purple",
  indigo: "bg-indigo-tint text-indigo",
  cyan: "bg-cyan-tint text-cyan",
  warn: "bg-warn-tint text-warn",
  critical: "bg-critical-tint text-critical",
};

/**
 * A titled region of a page. Sections give a page structure above the level of individual cards,
 * so a dense screen reads as a few purposeful areas rather than a uniform grid.
 */
export function Section({
  title,
  description,
  icon: Icon,
  accent = "accent",
  actions,
  children,
  className,
}: SectionProps): JSX.Element {
  return (
    <section className={cn("mt-8 first:mt-0", className)}>
      <header className="workspace-section-header mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {Icon ? (
            <span
              aria-hidden="true"
              className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-control", ACCENTS[accent])}
            >
              <Icon className="h-4 w-4" />
            </span>
          ) : null}
          <div className="min-w-0">
            <h2 className="text-section font-semibold leading-tight text-ink">{title}</h2>
            {description ? <p className="text-meta text-ink-muted">{description}</p> : null}
          </div>
        </div>
        {actions ? <div className="flex max-w-full flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

/** A compact statistic for use inside a section header strip. */
export function StatTile({
  label,
  value,
  tone = "neutral",
  caption,
  onClick,
  active = false,
  href,
}: {
  label: string;
  value: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "critical" | "accent";
  caption?: string;
  onClick?: () => void;
  active?: boolean;
  href?: string;
}): JSX.Element {
  return <MetricCard label={label} value={value} tone={tone} caption={caption} onClick={onClick} active={active} href={href} size="compact" />;
}
