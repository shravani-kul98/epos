import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Field, Select } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { StatusBadge, confidenceTone, healthTone, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate, formatScore } from "@/lib/format";
import { useActionRegister, usePortfolio, useTaskRegister } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { Action, ProjectSummary, Task } from "@/types/api";

const COLUMNS: Column<ProjectSummary>[] = [
  {
    key: "project",
    header: "Project",
    value: (row) => row.project_name,
    cell: (row) => (
      <div className="min-w-0">
        <Link to={`/projects/${row.project_id}`} className="font-medium text-ink hover:text-accent">
          {row.project_name}
        </Link>
        <p className="text-meta text-ink-muted">
          {row.project_id} · {row.domain}
        </p>
      </div>
    ),
  },
  {
    key: "manager",
    header: "Manager",
    value: (row) => row.project_manager,
    cell: (row) => row.project_manager,
  },
  { key: "phase", header: "Phase", value: (row) => row.project_phase, cell: (row) => row.project_phase },
  {
    key: "priority",
    header: "Priority",
    value: (row) => row.business_priority,
    cell: (row) => <StatusBadge label={row.business_priority} tone="neutral" showIcon={false} />,
  },
  {
    key: "health",
    header: "Health",
    align: "right",
    value: (row) => row.assessment?.is_assessed === false ? "" : row.health_score,
    cell: (row) => row.assessment?.is_assessed === false ? <span title={row.assessment.reason} className="text-meta text-ink-secondary">Not yet assessed</span> : (
      <div className="flex items-center justify-end gap-2">
        <span data-numeric>{formatScore(row.health_score)}</span>
        <StatusBadge label={row.health_band} tone={healthTone(row.health_band)} />
      </div>
    ),
  },
  {
    key: "confidence",
    header: "Confidence",
    align: "right",
    value: (row) => row.assessment?.is_assessed === false ? "" : row.confidence_score,
    cell: (row) => row.assessment?.is_assessed === false ? <span className="text-meta text-ink-secondary">Not yet assessed</span> : <StatusBadge label={row.confidence_band} tone={confidenceTone(row.confidence_band)} />,
  },
  {
    key: "alerts",
    header: "Open alerts",
    align: "right",
    value: (row) => row.open_alert_count,
    cell: (row) => (
      <span data-numeric className={row.critical_alert_count > 0 ? "font-semibold text-critical" : ""}>
        {row.open_alert_count}
      </span>
    ),
  },
  {
    key: "forecast",
    header: "Forecast end",
    align: "right",
    value: (row) => row.forecast_end_date ?? "",
    cell: (row) => formatDate(row.forecast_end_date),
  },
];

export function ProjectsPage(): JSX.Element {
  const { can } = useAuth();
  const navigate = useNavigate();
  const portfolio = usePortfolio();
  const canCreate = can("project.create");
  const { params, update, clear } = useViewParams();
  const view=params.get("view") ?? "projects";
  const projectId=params.get("project") ?? "";
  const tasks=useTaskRegister(projectId||undefined,view==="blocked");
  const actions=useActionRegister(projectId||undefined,view==="actions");
  const projectName=(id:string)=>portfolio.data?.projects.find(project=>project.project_id===id)?.project_name ?? id;
  const blockedColumns: Column<Task>[] = [
    {key:"work",header:"Blocked item",value:r=>`${r.task_name} ${r.task_id}`,cell:r=><div className="max-w-lg"><p className="font-medium">{r.task_name}</p><p className="mt-1 text-meta text-ink-secondary">{r.task_id} · milestone {r.milestone_id}</p></div>},
    {key:"project",header:"Project",value:r=>projectName(r.project_id),cell:r=>projectName(r.project_id)},
    {key:"owner",header:"Owner",value:r=>r.owner??"",cell:r=>r.owner??"Unassigned"},
    {key:"state",header:"Recorded state",value:r=>r.status,cell:r=><StatusBadge label={r.status} tone={statusTone(r.status)}/>},
    {key:"forecast",header:"Forecast finish",value:r=>r.forecast_end_date,cell:r=>formatDate(r.forecast_end_date)},
    {key:"update",header:"Last update",value:r=>r.last_updated_date??"",cell:r=>formatDate(r.last_updated_date)},
  ];
  const actionColumns: Column<Action>[] = [
    {key:"action",header:"Action",value:r=>`${r.action_description} ${r.action_id}`,cell:r=><div className="max-w-lg"><p className="font-medium">{r.action_description}</p><p className="mt-1 text-meta text-ink-secondary">{r.action_id} · {r.source_reference??"No source reference"}</p></div>},
    {key:"project",header:"Project",value:r=>projectName(r.project_id),cell:r=>projectName(r.project_id)},
    {key:"owner",header:"Owner",value:r=>r.owner??"",cell:r=>r.owner??"Unassigned"},
    {key:"state",header:"State",value:r=>r.status,cell:r=><StatusBadge label={r.status} tone={statusTone(r.status)}/>},
    {key:"priority",header:"Priority",value:r=>r.priority,cell:r=>r.priority},
    {key:"due",header:"Due date",value:r=>r.due_date,cell:r=>formatDate(r.due_date)},
  ];

  return (
    <>
      <PageHeader
        title={view==="blocked"?"Blocked items":view==="actions"?"Action tracker":"Projects"}
        description={view==="blocked"?"Work explicitly marked blocked, with its owner and recorded milestone context.":view==="actions"?"Agreed follow-through across projects, ordered by the recorded due date.":"Every project in the workspace, with its calculated health and reporting confidence."}
        actions={
          canCreate ? (
            <Button variant="primary" onClick={() => navigate("/projects/new")}>
              <Plus aria-hidden="true" className="h-4 w-4" />
              Create project
            </Button>
          ) : null
        }
      />

      <div role="group" aria-label="Execution views" className="mb-4 flex flex-wrap gap-2">{[{id:"projects",label:"Projects"},{id:"blocked",label:"Blocked items"},{id:"actions",label:"Actions"}].map(item=><Button key={item.id} aria-pressed={view===item.id} variant={view===item.id?"primary":"secondary"} onClick={()=>update({view:item.id==="projects"?undefined:item.id})}>{item.label}</Button>)}</div>
      <FilterBar description="Execution scope" active={Boolean(projectId)} onClear={()=>clear(["project"])}>
        <Field label="Project" htmlFor="execution-project"><Select id="execution-project" value={projectId} onChange={e=>update({project:e.target.value})}><option value="">All projects</option>{(portfolio.data?.projects??[]).map(project=><option key={project.project_id} value={project.project_id}>{project.project_name}</option>)}</Select></Field>
      </FilterBar>

      {view==="blocked" ? <DataTable rows={tasks.data?.filter(task=>task.is_blocked)} columns={blockedColumns} rowKey={r=>r.task_id} onRowClick={r=>navigate(`/projects/${r.project_id}?tab=work&state=blocked&task=${encodeURIComponent(r.task_id)}`)} isLoading={tasks.isLoading} error={tasks.error} onRetry={()=>void tasks.refetch()} label="Blocked items" searchPlaceholder="Filter blocked items" initialSortKey="forecast" emptyTitle="No blocked work recorded" emptyDescription="No returned task is marked as blocked in this scope. Unblock targets are not inferred from forecast dates."/> : view==="actions" ? <DataTable rows={actions.data} columns={actionColumns} rowKey={r=>r.action_id} onRowClick={r=>navigate(`/projects/${r.project_id}?tab=team`)} isLoading={actions.isLoading} error={actions.error} onRetry={()=>void actions.refetch()} label="Portfolio actions" searchPlaceholder="Filter actions by owner or state" initialSortKey="due" emptyTitle="No actions recorded" emptyDescription="Agreed actions appear here with their recorded owner, due date and state."/> : (
      <DataTable
        rows={portfolio.data?.projects.filter(project=>!projectId||project.project_id===projectId)}
        columns={COLUMNS}
        rowKey={(row) => row.project_id}
        isLoading={portfolio.isLoading}
        error={portfolio.isError ? portfolio.error : undefined}
        onRetry={() => void portfolio.refetch()}
        searchPlaceholder="Filter by name, manager or domain"
        initialSortKey="health"
        emptyTitle="No projects yet"
        emptyDescription={
          canCreate
            ? "Create your first project to start tracking milestones, risks and delivery."
            : "Projects appear here once a project manager creates them."
        }
        emptyAction={
          canCreate ? (
            <Button variant="primary" onClick={() => navigate("/projects/new")}>
              Create project
            </Button>
          ) : undefined
        }
      />
      )}
    </>
  );
}
