import { formatDate, formatDays } from "@/lib/format";
import type { ScenarioComparison } from "@/types/api";

export function ScenarioTimeline({ projects }: { projects: ScenarioComparison[] }): JSX.Element {
  const dates=projects.flatMap(project=>[project.baseline_forecast_end_date,project.scenario_forecast_end_date]).filter((value):value is string=>Boolean(value)).sort();
  if(!dates.length) return <p className="text-body text-ink-secondary">Completion dates are not recorded for this result. No timeline has been estimated.</p>;
  const first=dates[0]!; const last=dates[dates.length-1]!;
  const timestamp=(value:string)=>Date.parse(`${value}T00:00:00Z`);
  const start=timestamp(first); const span=Math.max(1,timestamp(last)-start);
  const position=(value:string)=>((timestamp(value)-start)/span)*90+5;
  return <div className="space-y-4">
    <p className="text-meta text-ink-secondary">Baseline ○ and scenario ◆ completion dates share the same date scale.</p>
    {projects.map(project=><div key={project.project_id} className="rounded-control border border-line p-4">
      <p className="text-body font-medium">{project.project_name}</p>
      <div className="relative my-4 h-10 border-b border-line" role="img" aria-label={`${project.project_name}: baseline ${formatDate(project.baseline_forecast_end_date)}, scenario ${formatDate(project.scenario_forecast_end_date)}, ${formatDays(project.forecast_end_shift_days)} shift`}>
        {project.baseline_forecast_end_date ? <span className="absolute bottom-2 -translate-x-1/2 text-section text-domain-schedule" style={{left:`${position(project.baseline_forecast_end_date)}%`}}>○</span> : null}
        {project.scenario_forecast_end_date ? <span className="absolute bottom-2 -translate-x-1/2 text-section text-domain-scenarios" style={{left:`${position(project.scenario_forecast_end_date)}%`}}>◆</span> : null}
      </div>
      <dl className="grid grid-cols-2 gap-4 text-meta"><div><dt className="text-ink-secondary">Baseline</dt><dd className="mt-1 tabular-nums">{formatDate(project.baseline_forecast_end_date)}</dd></div><div><dt className="text-ink-secondary">Scenario</dt><dd className="mt-1 tabular-nums">{formatDate(project.scenario_forecast_end_date)}</dd></div></dl>
      <p className="mt-3 text-meta text-ink-secondary">Calculated completion movement: {formatDays(project.forecast_end_shift_days)}</p>
    </div>)}
    <p className="flex justify-between text-meta text-ink-secondary"><span>{formatDate(first)}</span><span>{formatDate(last)}</span></p>
  </div>;
}