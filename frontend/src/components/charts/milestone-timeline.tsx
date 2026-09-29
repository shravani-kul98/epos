import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { daysUntil, formatDate } from "@/lib/format";
import type { Milestone } from "@/types/api";

/**
 * Milestone slip. Each row compares the stored baseline date with the stored forecast date, so the
 * bar length reflects recorded dates rather than any browser-side estimate.
 */
export function MilestoneTimeline({
  milestones,
  asOfDate,
}: {
  milestones: Milestone[];
  asOfDate: string;
}): JSX.Element {
  const rows = milestones
    .map((milestone) => ({
      milestone,
      slip: milestone.forecast_variance_days,
    }))
    .sort((left, right) => (right.slip ?? 0) - (left.slip ?? 0));

  const worst = Math.max(1, ...rows.map((row) => Math.abs(row.slip ?? 0)));

  return (
    <ul className="divide-y divide-line">
      {rows.map(({ milestone, slip }) => {
        const remaining = daysUntil(milestone.forecast_date, asOfDate);
        return (
          <li key={milestone.milestone_id} className="py-2.5 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-body font-medium text-ink">{milestone.milestone_name}</p>
                <p className="mt-0.5 text-meta text-ink-secondary">
                  Baseline {formatDate(milestone.baseline_date)} · Forecast{" "}
                  {formatDate(milestone.forecast_date)}
                </p>
              </div>
              <StatusBadge label={milestone.status} tone={statusTone(milestone.status)} />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-subtle">
                <div
                  className={cn("h-full rounded-full", (slip ?? 0) > 0 ? "bg-critical" : "bg-domain-schedule")}
                  style={{ width: `${Math.min(100, (Math.abs(slip ?? 0) / worst) * 100)}%` }}
                  role="presentation"
                />
              </div>
              <span
                className={cn("w-28 shrink-0 text-right text-meta", (slip ?? 0) > 0 ? "text-critical" : "text-ink-secondary")}
                data-numeric
              >
                {slip == null ? "Variance unavailable" : slip > 0 ? `${slip} days late` : slip < 0 ? `${Math.abs(slip)} days early` : "On baseline"}
              </span>
            </div>
            {remaining !== null && remaining < 0 && !milestone.actual_date && !["complete", "completed"].includes(milestone.status.toLowerCase()) ? (
              <p className="mt-1 text-meta text-critical" data-numeric>
                Forecast date passed {Math.abs(remaining)} days ago.
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
