import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  parseISO,
  startOfMonth,
  startOfWeek,
} from "date-fns";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Select } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/loading-skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format";
import {
  useChangeRequests,
  useMilestoneRegister,
  usePortfolio,
  useRiskRegister,
  useTaskRegister,
} from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";

type EntryKind = "milestone" | "task" | "risk" | "change";

interface Entry {
  id: string;
  kind: EntryKind;
  date: string;
  title: string;
  projectId: string;
  href: string;
}

const KIND_STYLES: Record<EntryKind, { label: string; dot: string; chip: string }> = {
  milestone: { label: "Milestone forecast", dot: "bg-accent", chip: "bg-accent-tint text-accent" },
  task: { label: "Task forecast", dot: "bg-accent", chip: "bg-accent-tint text-accent" },
  risk: { label: "Risk due", dot: "bg-critical", chip: "bg-critical-tint text-critical" },
  change: { label: "Change raised", dot: "bg-advisory", chip: "bg-advisory-tint text-advisory" },
};

/**
 * Programme calendar. Every entry is a date already stored against a record; nothing is inferred
 * and no scheduling is performed here.
 */
export function CalendarPage(): JSX.Element {
  const portfolio = usePortfolio();
  const projects = useMemo(() => portfolio.data?.projects ?? [], [portfolio.data]);
  const { params, update } = useViewParams();
  const projectId=params.get("project")??"";
  const monthParam=params.get("month");
  const month=useMemo(()=>monthParam&&/^\d{4}-(0[1-9]|1[0-2])$/.test(monthParam) ? parseISO(`${monthParam}-01`) : portfolio.data?.as_of_date ? parseISO(portfolio.data.as_of_date) : null,[monthParam,portfolio.data?.as_of_date]);
  const kindParam=params.get("kinds");
  const kinds=useMemo(()=>new Set((kindParam?.split(",")??["milestone","task","risk","change"]).filter((value):value is EntryKind=>value in KIND_STYLES)),[kindParam]);
  const [selected, setSelected] = useState<string | null>(null);

  const milestones = useMilestoneRegister(projectId||undefined);
  const tasks = useTaskRegister(projectId||undefined);
  const risks = useRiskRegister(projectId||undefined);
  const changes = useChangeRequests(projectId||undefined);

  const isLoading =
    portfolio.isLoading || milestones.isLoading || tasks.isLoading || risks.isLoading || changes.isLoading;
  const error=portfolio.error ?? milestones.error ?? tasks.error ?? risks.error ?? changes.error;

  const entries = useMemo<Entry[]>(() => {
    const all: Entry[] = [];
    for (const m of milestones.data ?? []) {
      if (m.forecast_date) {
        all.push({
          id: m.milestone_id,
          kind: "milestone",
          date: m.forecast_date,
          title: m.milestone_name,
          projectId: m.project_id,
          href: `/projects/${m.project_id}?tab=work`,
        });
      }
    }
    for (const t of tasks.data ?? []) {
      all.push({
        id: t.task_id,
        kind: "task",
        date: t.forecast_end_date,
        title: t.task_name,
        projectId: t.project_id,
        href: `/projects/${t.project_id}?tab=work`,
      });
    }
    for (const r of risks.data ?? []) {
      all.push({
        id: r.risk_id,
        kind: "risk",
        date: r.due_date,
        title: r.risk_name,
        projectId: r.project_id,
        href: `/projects/${r.project_id}?tab=risks`,
      });
    }
    for (const c of changes.data ?? []) {
      all.push({
        id: c.change_request_id,
        kind: "change",
        date: c.requested_date,
        title: c.change_description,
        projectId: c.project_id,
        href: `/projects/${c.project_id}?tab=changes`,
      });
    }
    return all.filter((entry) => kinds.has(entry.kind));
  }, [milestones.data, tasks.data, risks.data, changes.data, kinds]);

  const days = useMemo(() => {
    if (!month) return [];
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
    return eachDayOfInterval({ start, end });
  }, [month]);

  function entriesOn(day: Date): Entry[] {
    return entries.filter((entry) => {
      try {
        return isSameDay(parseISO(entry.date), day);
      } catch {
        return false;
      }
    });
  }

  function toggleKind(kind: EntryKind): void {
    const next=new Set(kinds);
    if(next.has(kind))next.delete(kind);else next.add(kind);
    update({kinds:[...next].join(",")||"none"});
  }

  const selectedEntries = selected
    ? entries.filter((entry) => entry.date === selected)
    : [];
  const monthEntries=entries.filter(entry=>month&&entry.date.startsWith(format(month,"yyyy-MM"))).sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id));

  return (
    <>
      <PageHeader
        title="Calendar"
        description="Forecast milestones and tasks, risk due dates, and the dates changes were raised."
        scope={projects.find(project=>project.project_id===projectId)?.project_name ?? "All accessible projects"}
        actions={
          <div className="flex items-center gap-1">
            <Button size="sm" disabled={!month} onClick={() => {if(month)update({month:format(addMonths(month,-1),"yyyy-MM")});}} aria-label="Previous month">
              <ChevronLeft aria-hidden="true" className="h-4 w-4" />
            </Button>
            <span className="min-w-[9rem] text-center text-body font-medium text-ink">
              {month ? format(month, "MMMM yyyy") : "Loading dates"}
            </span>
            <Button size="sm" disabled={!month} onClick={() => {if(month)update({month:format(addMonths(month,1),"yyyy-MM")});}} aria-label="Next month">
              <ChevronRight aria-hidden="true" className="h-4 w-4" />
            </Button>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="max-w-xs flex-1">
          <label htmlFor="calendar-project" className="mb-1 block text-meta font-medium text-ink">
            Project
          </label>
          <Select id="calendar-project" value={projectId} onChange={(e) => update({project:e.target.value})}>
            <option value="">All projects</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(KIND_STYLES) as EntryKind[]).map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => toggleKind(kind)}
              aria-pressed={kinds.has(kind)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-meta font-medium transition-colors",
                kinds.has(kind)
                  ? "border-line-strong bg-surface text-ink"
                  : "border-line bg-surface-subtle text-ink-muted",
              )}
            >
              <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", KIND_STYLES[kind].dot)} />
              {KIND_STYLES[kind].label}
            </button>
          ))}
        </div>
      </div>

      {error ? <ErrorState error={error} onRetry={()=>{void portfolio.refetch();void milestones.refetch();void tasks.refetch();void risks.refetch();void changes.refetch();}}/> : isLoading ? (
        <Skeleton className="h-[32rem] w-full" />
      ) : (
        <Card className="hidden overflow-hidden sm:block">
          <div className="grid grid-cols-7 border-b border-line bg-surface-subtle">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((label) => (
              <div
                key={label}
                className="px-2 py-2 text-center text-meta font-semibold uppercase tracking-wide text-ink-muted"
              >
                {label}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {days.map((day) => {
              const dayEntries = entriesOn(day);
              const inMonth = month ? isSameMonth(day, month) : false;
              const iso = format(day, "yyyy-MM-dd");
              return (
                <button
                  key={iso}
                  type="button"
                  onClick={() => setSelected(dayEntries.length > 0 ? iso : null)}
                  aria-label={`${formatDate(iso)}: ${dayEntries.length} recorded items`}
                  aria-pressed={selected===iso}
                  className={cn(
                    "min-h-[6.5rem] border-b border-r border-line p-1.5 text-left align-top transition-colors last:border-r-0",
                    inMonth ? "bg-surface" : "bg-surface-subtle/60",
                    dayEntries.length > 0 && "hover:bg-accent-tint",
                  )}
                >
                  <span
                    className={cn(
                      "text-meta",
                      inMonth ? "text-ink" : "text-ink-muted",
                    )}
                    data-numeric
                  >
                    {format(day, "d")}
                  </span>
                  <span className="mt-1 block space-y-1">
                    {dayEntries.slice(0, 3).map((entry) => (
                      <span
                        key={`${entry.kind}-${entry.id}`}
                        className={cn(
                          "block truncate rounded px-1.5 py-0.5 text-meta",
                          KIND_STYLES[entry.kind].chip,
                        )}
                        title={entry.title}
                      >
                        {entry.title}
                      </span>
                    ))}
                    {dayEntries.length > 3 ? (
                      <span className="block px-1.5 text-meta text-ink-muted">
                        {dayEntries.length - 3} more
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        </Card>
      )}

      {!isLoading && !error ? <section className="mt-4 rounded-card border border-line bg-surface p-4" aria-label="Monthly agenda"><h2 className="text-card font-medium">Agenda · {month ? format(month,"MMMM yyyy") : ""}</h2><p className="mt-1 text-meta text-ink-secondary">A readable list alternative to the calendar.</p>{monthEntries.length ? <ul className="mt-3 divide-y divide-line">{monthEntries.map(entry=><li key={`${entry.kind}-${entry.id}`} className="flex flex-wrap items-start gap-3 py-3"><time className="text-meta tabular-nums text-ink-secondary" dateTime={entry.date}>{formatDate(entry.date)}</time><div className="min-w-0 flex-1 basis-48"><Link to={entry.href} className="font-medium text-accent hover:underline">{entry.title}</Link><p className="mt-1 text-meta text-ink-secondary">{KIND_STYLES[entry.kind].label} · {entry.projectId} · {entry.id}</p></div></li>)}</ul> : <p className="mt-4 text-body text-ink-secondary">No selected record dates fall in this month. Change the month or filters to explore other dates.</p>}</section> : null}

      {!isLoading && !error && entries.length === 0 ? (
        <Card className="mt-4">
          <EmptyState
            title="Nothing scheduled"
            description="Recorded forecast, due and raised dates appear here. No review date is inferred from another date field."
          />
        </Card>
      ) : null}

      {selected && selectedEntries.length > 0 ? (
        <Card className="mt-4">
          <CardBody>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-card font-semibold text-ink">{formatDate(selected)}</h2>
              <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                Clear
              </Button>
            </div>
            <ul className="divide-y divide-line">
              {selectedEntries.map((entry) => (
                <li key={`${entry.kind}-${entry.id}`} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <Link to={entry.href} className="text-body font-medium text-ink hover:text-accent">
                      {entry.title}
                    </Link>
                    <p className="text-meta text-ink-muted">
                      {entry.projectId} · {entry.id}
                    </p>
                  </div>
                  <StatusBadge label={KIND_STYLES[entry.kind].label} tone="neutral" showIcon={false} />
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}
    </>
  );
}
