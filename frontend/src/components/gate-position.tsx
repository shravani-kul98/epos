import { Link } from "react-router-dom";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/loading-skeleton";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { SourceList } from "@/components/ui/source-list";
import { useGateReadiness } from "@/lib/queries";
import type { Gate } from "@/types/api";

export function GatePosition({ gate }: { gate: Gate }): JSX.Element {
  const readiness=useGateReadiness(gate.gate_id);
  const result=readiness.data;
  return <article className="rounded-control border border-line p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><Link to={`/projects/${gate.project_id}?tab=gates`} className="text-body font-medium text-accent hover:underline">{gate.gate_name}</Link><StatusBadge label={gate.status} tone={statusTone(gate.status)}/></div>
    <p className="mt-1 text-meta text-ink-secondary">{gate.owner} · {gate.gate_id}</p>
    {readiness.isError ? <ErrorState error={readiness.error} onRetry={()=>void readiness.refetch()}/> : !result ? <Skeleton className="mt-3 h-16 w-full"/> : <>
      <p className="mt-3 text-body font-medium">{result.state}</p>
      {result.blockers.length ? <div className="mt-3 rounded-control border border-critical bg-critical-tint p-3"><p className="font-medium text-critical">Mandatory blockers remain</p><ul className="mt-2 list-disc space-y-1 pl-4 text-body">{result.blockers.map(blocker=><li key={blocker.message}>{blocker.message}<SourceList ids={blocker.source_ids} className="mt-1"/></li>)}</ul></div> : null}
      <p className="mt-3 text-meta text-ink-secondary">{result.percentage===null ? "Readiness percentage unavailable; review the criteria." : `${result.percentage}% of assessed criteria complete. A percentage cannot override a mandatory blocker.`}</p>
      <p className="mt-2 text-meta text-ink-secondary">Human review: {result.latest_review_outcome ?? "Not recorded"}</p>
    </>}
  </article>;
}