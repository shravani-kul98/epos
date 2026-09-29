import { formatDate, formatPercent } from "@/lib/format";
import { StatusBadge } from "@/components/ui/status-badge";
import { SourceList } from "@/components/ui/source-list";
import type { ResourceAllocation } from "@/types/api";

export function CapacityMatrix({ records }: { records: ResourceAllocation[] }): JSX.Element {
  const weeks=[...new Set(records.map(row=>row.week_start_date))].sort();
  const resourceIds=[...new Set(records.map(row=>row.resource_id))];
  return <div>
    <div role="region" aria-label="Weekly capacity matrix" tabIndex={0} className="overflow-x-auto rounded-control border border-line">
      <table className="w-full border-collapse text-left text-body"><caption className="sr-only">Resource utilisation from weekly allocation records</caption>
        <thead className="bg-surface-subtle"><tr><th scope="col" className="p-3 font-medium">Resource</th>{weeks.map(week=><th key={week} scope="col" className="whitespace-nowrap p-3 text-meta font-medium">Week of {formatDate(week)}</th>)}</tr></thead>
        <tbody>{resourceIds.map(id=><tr key={id} className="border-t border-line"><th scope="row" className="p-3 font-medium">{records.find(row=>row.resource_id===id)?.resource_name}<p className="text-meta font-normal text-ink-secondary">{id}</p></th>{weeks.map(week=>{
          const entries=records.filter(row=>row.resource_id===id&&row.week_start_date===week);
          return <td key={week} className="p-2">{entries.length ? entries.map((row,index)=><div key={`${row.project_id}-${index}`} className={`rounded-control p-3 ${row.is_overallocated?"bg-critical-tint":"bg-cyan-tint"}`}>
            <p className="font-medium tabular-nums">{formatPercent(row.utilisation_percent)}</p><p className="mt-1 whitespace-nowrap text-meta text-ink-secondary">{row.allocated_hours} / {row.capacity_hours} hours</p>
            <StatusBadge label={row.is_overallocated?"Over capacity":"Within recorded capacity"} tone={row.is_overallocated?"critical":"accent"} className="mt-2"/>
          </div>) : <span className="text-meta text-ink-muted">Not recorded</span>}</td>;
        })}</tr>)}</tbody>
      </table>
    </div>
    <p className="mt-3 text-meta text-ink-secondary">Utilisation and over-capacity flags are calculated from the recorded weekly hours. No unstaffed demand or skill gap is estimated.</p>
    <SourceList ids={resourceIds} className="mt-3" label="Allocation records"/>
  </div>;
}