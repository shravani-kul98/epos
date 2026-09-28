import { Link } from "react-router-dom";
import { ArrowRight, FileCheck2, MessageSquare } from "lucide-react";

import { Skeleton } from "@/components/ui/loading-skeleton";
import { formatDate, formatScore } from "@/lib/format";
import type { PortfolioDashboard } from "@/types/api";

/**
 * A short read on the portfolio, assembled from figures the API calculated. Sentences are
 * composed from those values; nothing here estimates or predicts.
 */
function briefing(data: PortfolioDashboard): { headline: string; risks: string[]; action: string | null } {
  const assessed = data.projects.filter(project => project.assessment?.is_assessed !== false);
  const red = assessed.filter((p) => p.health_band === "Red");
  const lowConfidence = assessed.filter((p) => p.confidence_band === "Low");
  const critical = data.alert_severities.critical;

  const amber = data.health_bands.amber;
  const headline =
    data.project_count === 0
      ? "There are no projects in this workspace yet. Create a project to start the delivery read."
      : data.unassessed_count === data.project_count
      ? "No project has delivery records yet. Add a milestone or task before interpreting health scores."
      : red.length === 0
      ? `No assessed project is in the red band. ${amber} of ${assessed.length} ${amber === 1 ? "is" : "are"} amber and worth watching.`
      : `${red.length} of ${assessed.length} assessed ${assessed.length === 1 ? "project is" : "projects are"} in the red band${amber ? ` and ${amber} ${amber === 1 ? "is" : "are"} amber` : ""}.`;

  const risks: string[] = [];
  if (data.unassessed_count) risks.push(`${data.unassessed_count} ${data.unassessed_count === 1 ? "project is" : "projects are"} not yet assessed and excluded from the health band totals.`);
  const weakest = red[0] ?? assessed.slice().sort((a, b) => a.health_score - b.health_score)[0];
  if (weakest) {
    risks.push(
      `${weakest.project_name} scores ${formatScore(weakest.health_score)} with ${weakest.open_alert_count} open ${weakest.open_alert_count === 1 ? "alert" : "alerts"}.`,
    );
  }
  if (critical > 0) {
    risks.push(`${critical} critical ${critical === 1 ? "alert is" : "alerts are"} open across the portfolio.`);
  }
  if (lowConfidence.length > 0) {
    risks.push(
      `${lowConfidence.length} ${lowConfidence.length === 1 ? "project has" : "projects have"} weak reporting, which limits how far the delivery read can be trusted.`,
    );
  }

  const action = weakest
    ? `Review ${weakest.project_name} and its supporting records with its manager.`
    : null;

  return { headline, risks, action };
}

export function EposBriefing({
  data,
  isLoading,
  canAsk = true,
}: {
  data: PortfolioDashboard | undefined;
  isLoading: boolean;
  canAsk?: boolean;
}): JSX.Element {
  if (isLoading || !data) {
    return (
      <section className="rounded-card border border-accent-border bg-accent-tint p-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-3 h-5 w-3/4" />
        <Skeleton className="mt-2 h-4 w-1/2" />
      </section>
    );
  }

  const { headline, risks, action } = briefing(data);

  return (
    <section
      aria-label="EPOS briefing"
      className="workspace-briefing h-full rounded-card border border-accent-border bg-accent-tint p-5"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-card font-semibold text-ink">
          <FileCheck2 aria-hidden="true" className="h-4 w-4 text-accent" />
          Calculated portfolio position
        </h2>
        <span className="text-meta text-ink-muted">As at {formatDate(data.as_of_date)}</span>
      </div>

      <p className="mt-2 text-body font-medium text-ink">{headline}</p>

      {risks.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {risks.map((line) => (
            <li key={line} className="flex gap-2 text-body text-ink-secondary">
              <span aria-hidden="true" className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />
              {line}
            </li>
          ))}
        </ul>
      ) : null}

      {action ? (
        <p className="mt-2 text-body text-ink">
          <span className="font-medium">Recommended: </span>
          {action}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link to="/portfolio" className="inline-flex min-h-10 items-center gap-2 rounded-control border border-line bg-surface px-3 py-2 text-meta font-medium text-ink hover:border-accent">
          View evidence <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
        </Link>
        {canAsk ? <Link to="/ask" className="inline-flex min-h-10 items-center gap-2 rounded-control px-3 py-2 text-meta font-medium text-accent hover:bg-surface">
          <MessageSquare aria-hidden="true" className="h-3.5 w-3.5" />Ask EPOS
        </Link> : null}
        <span className="text-meta text-ink-muted">Calculated facts · not an AI explanation</span>
      </div>
    </section>
  );
}
