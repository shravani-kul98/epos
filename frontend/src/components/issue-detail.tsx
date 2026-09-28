import { LifecycleSection, type LifecycleMove } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, severityTone, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useTransitionIssue } from "@/lib/queries";
import type { Issue } from "@/types/api";

// Mirrors the issue lifecycle the API enforces, so only accepted steps are offered.
const ISSUE_MOVES: readonly LifecycleMove[] = [
  { target: "In Progress", label: "Start work", from: ["Open"], reasonOptional: true },
  {
    target: "Resolved", label: "Resolve", from: ["Open", "In Progress"], reasonLabel: "Resolution summary",
    reasonHint: "What resolved it. Saved as the issue's recorded resolution.",
  },
  { target: "Open", label: "Return to open", from: ["In Progress"] },
  { target: "Closed", label: "Close issue", from: ["Resolved"], reasonLabel: "Closing note", reasonHint: "Why no further work is needed." },
  { target: "In Progress", label: "Reopen", from: ["Resolved"], reasonHint: "What showed the resolution did not hold." },
  { target: "Open", label: "Reopen", from: ["Closed"], reasonHint: "What showed the issue has returned." },
];

export function IssueDetail({ issue, onClose, onEdit }: { issue: Issue; onClose: () => void; onEdit?: () => void }): JSX.Element {
  const { can } = useAuth();
  const transition = useTransitionIssue();
  const sourceRisk = issue.source_reference?.match(/^Risk (\S+)$/)?.[1];
  return <Drawer open onClose={onClose} busy={transition.isPending} title={issue.title} description={`${issue.issue_id} · ${issue.project_id}`}>
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2"><StatusBadge label={issue.severity} tone={severityTone(issue.severity)}/><StatusBadge label={issue.status} tone={statusTone(issue.status)}/>
        {onEdit && can("issue.manage") ? <Button size="sm" className="ml-auto" onClick={onEdit}>Edit issue</Button> : null}</div>
      <p className="whitespace-pre-wrap text-body">{issue.description}</p>
      <dl className="grid grid-cols-2 gap-4">{[
        ["Owner",issue.owner??"Unassigned"],["Raised",formatDate(issue.raised_date)],
        ["Target resolution",formatDate(issue.target_resolution_date)],["Resolved by",issue.resolved_by??"Not recorded"],
        ["Resolution date",formatDate(issue.resolved_at)],[sourceRisk ? "Came from risk" : "Source reference",sourceRisk ?? issue.source_reference??"Not recorded"],
      ].map(([label,value])=><div key={label}><dt className="text-meta text-ink-secondary">{label}</dt><dd className="mt-1 break-words text-body">{value}</dd></div>)}</dl>
      <section><h3 className="text-card font-medium">Resolution evidence</h3><p className="mt-2 text-body text-ink-secondary">{issue.resolution_summary??"No resolution summary has been recorded. A closed label alone is not evidence."}</p></section>
      {can("issue.manage") ? <LifecycleSection key={`${issue.issue_id}-${issue.status}`} status={issue.status} moves={ISSUE_MOVES} recordLabel={issue.issue_id}
        disabled={issue.row_version == null} pending={transition.isPending}
        onConfirm={(move, reason) => transition.mutateAsync({ issue, target: move.target, rationale: reason })} /> : null}
      <SourceList ids={[issue.issue_id,issue.project_id]} label="Record context"/>
    </div>
  </Drawer>;
}