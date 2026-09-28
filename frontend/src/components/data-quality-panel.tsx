import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, confidenceTone, severityTone } from "@/components/ui/status-badge";
import { formatScore } from "@/lib/format";
import type { ConfidenceResult, Severity } from "@/types/api";

const ORDER: Record<Severity, number> = { Critical:0, High:1, Medium:2, Low:3 };

export function DataQualityPanel({ confidence }: { confidence: ConfidenceResult }): JSX.Element {
  const issues=confidence.data_quality_issues.slice().sort((a,b)=>ORDER[a.severity]-ORDER[b.severity]);
  return <section aria-label="Data quality correction list" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-card font-medium">Reporting confidence</h3><p className="mt-1 text-meta text-ink-secondary">Fix the records below; no score improvement is estimated.</p></div><StatusBadge label={`${formatScore(confidence.score)} / 100 · ${confidence.band}`} tone={confidenceTone(confidence.band)}/></div>
    {issues.length ? <ol className="divide-y divide-line">{issues.map(issue=><li key={`${issue.issue_type}-${issue.message}`} className="py-4">
      <div className="flex items-start justify-between gap-3"><p className="text-body font-medium">{issue.message}</p><StatusBadge label={issue.severity} tone={severityTone(issue.severity)}/></div>
      <p className="mt-2 text-body text-ink-secondary">{issue.remediation_hint}</p>
      <SourceList ids={issue.source_ids} label="Inspect affected records" className="mt-3"/>
    </li>)}</ol> : <p className="rounded-control bg-surface-subtle p-4 text-body text-ink-secondary">No information-quality findings were returned by the current assessment.</p>}
  </section>;
}