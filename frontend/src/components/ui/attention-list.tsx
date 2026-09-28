import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, severityTone } from "@/components/ui/status-badge";
import { formatDate } from "@/lib/format";
import type { Alert, ProjectSummary } from "@/types/api";

export function AttentionList({ alerts, projects, limit = 6 }: {
  alerts: Alert[];
  projects: ProjectSummary[];
  limit?: number;
}): JSX.Element {
  return <div>
    <ol className="divide-y divide-line">{alerts.slice(0, limit).map((alert) => {
      const project = projects.find((item) => item.project_id === alert.project_id);
      return <li key={alert.alert_id} className="py-4 first:pt-0">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1 basis-48">
            <Link to={`/projects/${alert.project_id}`} className="text-card font-medium text-ink hover:text-accent">{project?.project_name ?? alert.project_id}<ArrowUpRight className="ml-1 inline" size={14} aria-hidden="true" /></Link>
            <p className="mt-1 text-meta text-ink-secondary">{project ? `Project manager: ${project.project_manager} · ` : ""}{alert.project_id}</p>
          </div>
          <StatusBadge label={alert.severity} tone={severityTone(alert.severity)} />
        </div>
        <p className="mt-2 text-body font-medium">{alert.title}</p>
        <details className="mt-2 text-body">
          <summary className="cursor-pointer text-meta text-accent">Why this needs attention</summary>
          <p className="mt-2 text-ink-secondary">{alert.explanation}</p>
          <p className="mt-2 text-ink-secondary">{alert.recommended_next_step}</p>
          <p className="mt-2 text-meta text-ink-muted">Analysis date {formatDate(alert.as_of_date)}</p>
        </details>
        <SourceList ids={alert.source_ids} className="mt-2" />
      </li>;
    })}</ol>
    {alerts.length > limit ? <p className="border-t border-line pt-3 text-meta text-ink-secondary">Showing {limit} of {alerts.length} supplied alerts. Open the project for its complete assessment.</p> : null}
  </div>;
}