import { useMemo } from "react";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { RecordReference } from "@/components/ui/record-reference";
import { formatDate } from "@/lib/format";
import type { Milestone, Task } from "@/types/api";

interface TimelineRecord {
  id: string;
  name: string;
  type: string;
  status: string;
  plannedStart: string | null;
  plannedEnd: string | null;
  forecastStart: string | null;
  forecastEnd: string | null;
  actualStart: string | null;
  actualEnd: string | null;
  parent: string | null;
}

const timestamp = (value: string) => Date.parse(`${value}T00:00:00Z`);

export function DeliveryTimeline({ milestones, tasks, asOfDate, projectStart }: {
  milestones: Milestone[];
  tasks: Task[];
  asOfDate: string;
  /** The project's start, so the axis shows the whole plan rather than only the recorded dates. */
  projectStart?: string | null;
}): JSX.Element {
  const records = useMemo<TimelineRecord[]>(() => [
    ...milestones.map(m => ({ id:m.milestone_id,name:m.milestone_name,type:"Milestone",status:m.status,plannedStart:null,plannedEnd:m.baseline_date,forecastStart:null,forecastEnd:m.forecast_date,actualStart:null,actualEnd:m.actual_date,parent:null })),
    ...tasks.map(t => ({ id:t.task_id,name:t.task_name,type:"Task",status:t.status,plannedStart:t.planned_start_date,plannedEnd:t.planned_end_date,forecastStart:t.forecast_start_date,forecastEnd:t.forecast_end_date,actualStart:t.actual_start_date,actualEnd:t.actual_end_date,parent:t.parent_task_id ?? null })),
  ], [milestones,tasks]);
  const recorded = records.flatMap(r => [r.plannedStart,r.plannedEnd,r.forecastStart,r.forecastEnd,r.actualStart,r.actualEnd]);
  if (!recorded.some(value => Boolean(value) && Number.isFinite(timestamp(value!)))) return <p className="p-4 text-body text-ink-secondary">No recorded dates are available for a timeline. The records remain available in the table view.</p>;
  // The axis always reaches back to the project start and forward to today.
  const dates = [...recorded, projectStart ?? null, asOfDate].filter((value): value is string => Boolean(value) && Number.isFinite(timestamp(value!))).sort();
  const first = dates[0]!;
  const last = dates[dates.length-1]!;
  const min = timestamp(first);
  const span = Math.max(1,timestamp(last)-min);
  const position = (date: string) => Math.max(0,Math.min(100,((timestamp(date)-min)/span)*100));
  const ids = new Set(records.map(record=>record.id));

  function marks(record: TimelineRecord): JSX.Element {
    const series = [
      {label:record.type === "Milestone" ? "Baseline" : "Planned",start:record.plannedStart,end:record.plannedEnd,color:"bg-domain-governance",top:"top-1"},
      {label:"Forecast",start:record.forecastStart,end:record.forecastEnd,color:"bg-domain-schedule",top:"top-4"},
      {label:"Actual",start:record.actualStart,end:record.actualEnd,color:"bg-domain-testing",top:"top-7"},
    ];
    return <div className="relative h-11 rounded-control border-x border-line bg-surface-subtle" role="img" aria-label={series.map(s=>`${s.label}: ${s.start ?? "start not recorded"} to ${s.end ?? "finish not recorded"}`).join(". ")}>
      {series.map(s => {
        const end=s.end ?? s.start;
        if (!end) return null;
        const start=s.start ?? end;
        const title = `${s.label}: ${formatDate(s.start)} → ${formatDate(s.end)}`;
        // A single date is a point in time; it reads as a marker rather than a hairline bar.
        if (start === end) return <span key={s.label} title={title} className={`absolute h-2.5 w-2.5 -translate-x-1/2 rotate-45 rounded-[2px] ${s.color} ${s.top}`} style={{left:`${position(end)}%`}} />;
        return <span key={s.label} title={title} className={`absolute h-2 min-w-1 rounded-sm ${s.color} ${s.top}`} style={{left:`${position(start)}%`,width:`${Math.max(0,position(end)-position(start))}%`,maxWidth:`${100-position(start)}%`}} />;
      })}
      {asOfDate >= first && asOfDate <= last ? <span aria-hidden="true" className="absolute inset-y-0 border-l-2 border-dashed border-accent" style={{left:`${position(asOfDate)}%`}} /> : null}
    </div>;
  }

  function recordView(record: TimelineRecord, visited: Set<string>): JSX.Element {
    if(visited.has(record.id)) return <p role="alert">Hierarchy could not be displayed. Use the full records table below.</p>;
    const next=new Set(visited).add(record.id);
    const children=records.filter(child=>child.parent===record.id);
    return <div key={record.id} className="border-t border-line py-3">
      <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(180px,1fr)_2fr]">
        <div className="min-w-0"><p className="break-words text-body font-medium">{record.name}</p><div className="mt-1 flex flex-wrap items-center gap-2"><span className="text-meta text-ink-secondary">{record.type}</span><StatusBadge label={record.status} tone={statusTone(record.status)} /></div><RecordReference references={[record.id]} /></div>
        {marks(record)}
      </div>
      {children.length ? <details open className="mt-3 border-l-2 border-line pl-4"><summary className="cursor-pointer text-meta text-accent">Child work · {children.length} records</summary>{children.map(child=>recordView(child,next))}</details> : null}
    </div>;
  }

  return <div className="min-w-0">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-meta text-ink-secondary">
      <p>Stored dates only · marks indicate dates without a recorded start.</p>
      <div className="flex flex-wrap gap-3"><span>Plan / baseline ▬</span><span className="text-domain-schedule">Forecast ▬</span><span className="text-domain-testing">Actual ▬</span><span>Dashed line: analysis date</span></div>
    </div>
    <div className="grid gap-3 md:grid-cols-[minmax(180px,1fr)_2fr]"><p className="text-meta font-medium">Delivery hierarchy</p><p className="flex justify-between text-meta tabular-nums text-ink-secondary"><time dateTime={first}>{formatDate(first)}</time><time dateTime={last}>{formatDate(last)}</time></p></div>
    {records.filter(record=>!record.parent || !ids.has(record.parent)).map(record=>recordView(record,new Set()))}
    <details className="disclosure mt-4"><summary>View timeline dates as table</summary>
      <div className="overflow-x-auto p-3"><table className="w-full text-left text-meta"><caption className="sr-only">Recorded delivery dates</caption>
        <thead><tr>{["Record","Planned / baseline start","Planned / baseline finish","Forecast start","Forecast finish","Actual start","Actual finish"].map(label=><th scope="col" key={label} className="p-2 font-medium">{label}</th>)}</tr></thead>
        <tbody>{records.map(record=><tr key={record.id} className="border-t border-line"><td className="p-2">{record.name}<p><code>{record.id}</code></p></td>{[record.plannedStart,record.plannedEnd,record.forecastStart,record.forecastEnd,record.actualStart,record.actualEnd].map((value,index)=><td key={index} className="whitespace-nowrap p-2 tabular-nums">{formatDate(value)}</td>)}</tr>)}</tbody>
      </table></div>
    </details>
  </div>;
}