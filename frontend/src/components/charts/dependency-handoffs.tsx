import { ArrowRight } from "lucide-react";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { formatDays } from "@/lib/format";
import type { Dependency } from "@/types/api";

export function DependencyHandoffs({ dependencies, names = {} }: {
  dependencies: Dependency[];
  /** Record names by reference, so a hand-off reads as work rather than as identifiers. */
  names?: Record<string, string>;
}): JSX.Element {
  const endpoint = (type: string, id: string) => <div className="min-w-0 rounded-control bg-surface-subtle p-3">
    <p className="text-ink-secondary">{type}</p>
    {names[id] ? <p className="break-words font-medium text-ink">{names[id]}</p> : null}
    <code>{id}</code>
  </div>;
  return <div className="space-y-3">
    <p className="text-meta text-ink-secondary">Recorded relationships only. Missing timing metadata is not treated as a scheduling assumption.</p>
    {dependencies.length ? dependencies.map(dependency=><article key={dependency.dependency_id} className="rounded-control border border-line p-4">
      <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="text-body font-medium">{dependency.dependency_name}</h3><StatusBadge label={dependency.status} tone={statusTone(dependency.status)}/></div>
      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-meta">{endpoint(dependency.predecessor_type, dependency.predecessor_id)}<ArrowRight aria-hidden="true" className="text-domain-schedule" size={18}/>{endpoint(dependency.successor_type, dependency.successor_id)}</div>
      <p className="mt-3 text-meta text-ink-secondary">{dependency.relationship_type ?? "Relationship timing not recorded"} · {dependency.lag_days==null?"Lag not recorded":`${formatDays(dependency.lag_days)} lag`} · recorded delay {formatDays(dependency.delay_days)}</p>
      <SourceList ids={[dependency.dependency_id,dependency.predecessor_id,dependency.successor_id]} className="mt-3"/>
    </article>) : <p className="text-body text-ink-secondary">No dependency records were returned for this scope.</p>}
    <details className="disclosure"><summary>View dependencies as table</summary><div className="overflow-x-auto p-3"><table className="w-full text-left text-meta"><caption className="sr-only">Recorded dependency hand-offs</caption><thead><tr>{["Dependency","Predecessor","Successor","Relationship","Lag"].map(label=><th scope="col" className="p-2 font-medium" key={label}>{label}</th>)}</tr></thead><tbody>{dependencies.map(dependency=><tr className="border-t border-line" key={dependency.dependency_id}><td className="p-2">{dependency.dependency_id}</td><td className="p-2">{dependency.predecessor_id}</td><td className="p-2">{dependency.successor_id}</td><td className="p-2">{dependency.relationship_type??"Not recorded"}</td><td className="p-2 tabular-nums">{dependency.lag_days??"—"}</td></tr>)}</tbody></table></div></details>
  </div>;
}