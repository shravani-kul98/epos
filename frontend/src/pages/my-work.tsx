import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ActionTransitionButtons } from "@/components/actions/action-transition-buttons";
import { DataTable, type Column } from "@/components/ui/data-table";
import { AssignmentAnswer } from "@/components/tasks/assignment-answer";
import { CompleteTaskButton } from "@/components/tasks/complete-task-button";
import { TaskEditor } from "@/components/tasks/task-editor";
import { TaskReviewBadge } from "@/components/tasks/task-review-actions";
import { Select } from "@/components/ui/form";
import { Field } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { Section } from "@/components/ui/section";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { daysUntil, formatDate } from "@/lib/format";
import { useActionRegister, useAssumptionRegister, useIssues, usePortfolio, useRiskRegister, useTaskRegister } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import { REVIEW_PENDING, isTaskClosed, isTaskComplete } from "@/lib/task-state";
import type { Action, Task } from "@/types/api";

const CLOSED_ACTION_STATUSES = ["complete", "closed", "cancelled"];
const ENDED_RECORD_STATUSES = ["closed", "accepted", "resolved", "retired", "validated", "invalidated"];

interface OwnedRecord {
  id: string;
  kind: "Risk" | "Issue" | "Assumption";
  title: string;
  projectId: string;
  status: string;
  due: string | null;
  tab: string;
}

function actionStatus(action: Action): string {
  return action.status.trim().toLowerCase();
}

/** Work assigned to the signed-in user's stable account identity. */
export function MyWorkPage(): JSX.Element {
  const { user, can } = useAuth();
  const [editing, setEditing] = useState<Task | null>(null);
  const [notice, setNotice] = useState("");
  const portfolio = usePortfolio();
  const projects = useMemo(() => portfolio.data?.projects ?? [], [portfolio.data]);
  const { params, update, clear } = useViewParams();
  const projectId = params.get("project") ?? "";
  const tasks = useTaskRegister(projectId || undefined);
  const actions = useActionRegister(projectId || undefined);
  const risks = useRiskRegister(projectId || undefined);
  const issues = useIssues(projectId || undefined);
  const assumptions = useAssumptionRegister(projectId || undefined);
  const view=params.get("view") ?? "all";
  const asOf = portfolio.data?.as_of_date ?? "";

  const mine = useMemo(() => {
    if (user?.id == null) return [];
    return (tasks.data ?? []).filter((task) => task.owner_user_id === user.id);
  }, [tasks.data, user]);

  const myActions = useMemo(() => {
    if (user?.id == null) return [];
    return (actions.data ?? []).filter((action) => action.owner_user_id === user.id);
  }, [actions.data, user]);

  const owned = useMemo<OwnedRecord[]>(() => {
    if (user?.id == null) return [];
    return [
      ...(risks.data ?? []).filter(risk => risk.risk_id && risk.mitigation_owner_user_id === user.id).map(risk => ({
        id: risk.risk_id, kind: "Risk" as const, title: risk.risk_name, projectId: risk.project_id, status: risk.status, due: risk.due_date, tab: "risks",
      })),
      ...(issues.data ?? []).filter(issue => issue.issue_id && issue.owner_user_id === user.id).map(issue => ({
        id: issue.issue_id, kind: "Issue" as const, title: issue.title, projectId: issue.project_id, status: issue.status, due: issue.target_resolution_date, tab: "issues",
      })),
      ...(assumptions.data ?? []).filter(item => item.assumption_id && item.owner_user_id === user.id).map(item => ({
        id: item.assumption_id, kind: "Assumption" as const, title: item.assumption_text, projectId: item.project_id, status: item.status, due: item.validation_due_date, tab: "assumptions",
      })),
    ].filter(record => !ENDED_RECORD_STATUSES.includes(record.status.trim().toLowerCase()));
  }, [risks.data, issues.data, assumptions.data, user]);

  // A task is due on its planned date; a later forecast is shown beside it, not instead of it.
  const remainingDays = (task: Task) => daysUntil(task.planned_end_date, asOf);
  const blocked = mine.filter((task) => task.is_blocked && !isTaskClosed(task));
  const overdue = mine.filter((task) => {
    const remaining = remainingDays(task);
    return remaining !== null && remaining < 0 && !isTaskClosed(task);
  });
  const dueSoon = mine.filter((task) => {
    const remaining = remainingDays(task);
    return remaining !== null && remaining >= 0 && remaining <= 14 && !isTaskClosed(task);
  });
  // Completed means accepted: work still waiting for its review is not yet done.
  const completed = mine.filter((task) => isTaskComplete(task) && task.review_status !== REVIEW_PENDING);
  const openActions = myActions.filter((action) => !CLOSED_ACTION_STATUSES.includes(actionStatus(action)));
  const blockedActions = openActions.filter((action) => actionStatus(action) === "blocked");
  const overdueActions = openActions.filter((action) => (daysUntil(action.due_date, asOf) ?? 0) < 0);
  const dueSoonActions = openActions.filter((action) => {
    const remaining = daysUntil(action.due_date, asOf);
    return remaining !== null && remaining >= 0 && remaining <= 14;
  });
  const completedActions = myActions.filter((action) => actionStatus(action) === "complete");
  const visible=view==="blocked"?blocked:view==="overdue"?overdue:view==="upcoming"?dueSoon:view==="completed"?completed:mine;
  const visibleActions=view==="blocked"?blockedActions:view==="overdue"?overdueActions:view==="upcoming"?dueSoonActions:view==="completed"?completedActions:myActions;
  const counted = (taskCount: number, actionCount: number) => (tasks.data && actions.data ? taskCount + actionCount : "—");

  const columns: Column<Task>[] = [
    {
      key: "task",
      header: "Task",
      value: (row) => row.task_name,
      cell: (row) => (
        <div className="min-w-0">
          <Link
            to={`/projects/${row.project_id}?tab=work&task=${encodeURIComponent(row.task_id)}`}
            className="font-medium text-ink hover:text-accent"
          >
            {row.task_name}
          </Link>
          <p className="text-meta text-ink-muted">{row.project_id}</p>
          {row.review_status === "Returned" && row.review_note ? (
            <p className="mt-1 max-w-md whitespace-pre-wrap text-meta text-critical">Returned: {row.review_note}</p>
          ) : null}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge label={row.status} tone={statusTone(row.status)} />
          {row.is_blocked ? <StatusBadge label="Blocked" tone="critical" /> : null}
          <TaskReviewBadge status={row.review_status} />
          {row.assignment_status === "Pending" ? <StatusBadge label="Awaiting your answer" tone="warn" /> : null}
        </div>
      ),
    },
    {
      key: "progress",
      header: "Progress",
      align: "right",
      value: (row) => row.completion_percent,
      cell: (row) => <span data-numeric>{row.completion_percent}%</span>,
    },
    {
      key: "due",
      header: "Due",
      align: "right",
      value: (row) => row.planned_end_date,
      cell: (row) => {
        const remaining = remainingDays(row);
        const late = remaining !== null && remaining < 0 && !isTaskClosed(row);
        return (
          <span className={cn(late && "font-medium text-critical")} data-numeric>
            {formatDate(row.planned_end_date)}
            {late ? ` · ${Math.abs(remaining)}d late` : ""}
            {row.forecast_end_date !== row.planned_end_date && !isTaskClosed(row)
              ? <span className="block text-meta font-normal text-ink-secondary">Forecast {formatDate(row.forecast_end_date)}</span>
              : null}
          </span>
        );
      },
    },
    {
      key: "actions", header: "Actions",
      cell: task => can("work.update") ? <div className="flex flex-wrap gap-2"><AssignmentAnswer task={task} />{task.assignment_status === "Pending" && task.owner_user_id === user?.id ? null : <><Button size="sm" onClick={() => setEditing(task)}>Update progress</Button><CompleteTaskButton task={task} /></>}</div> : <span className="text-meta text-ink-secondary">Read only</span>,
    },
  ];

  const actionColumns: Column<Action>[] = [
    {
      key: "action",
      header: "Action",
      value: (row) => `${row.action_description} ${row.action_id}`,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="font-medium text-ink">{row.action_description}</p>
          <p className="text-meta text-ink-muted">{row.action_id} · {row.project_id}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
    },
    {
      key: "due",
      header: "Due",
      align: "right",
      value: (row) => row.due_date,
      cell: (row) => {
        const remaining = daysUntil(row.due_date, asOf);
        const late = remaining !== null && remaining < 0 && !CLOSED_ACTION_STATUSES.includes(row.status.trim().toLowerCase());
        return (
          <span className={cn(late && "font-medium text-critical")} data-numeric>
            {formatDate(row.due_date)}
            {late ? ` · ${Math.abs(remaining)}d late` : ""}
          </span>
        );
      },
    },
    {
      key: "update", header: "Update",
      cell: (row) => can("work.update") ? <div className="flex flex-wrap gap-2"><ActionTransitionButtons action={row} /></div> : <span className="text-meta text-ink-secondary">Read only</span>,
    },
  ];

  const ownedColumns: Column<OwnedRecord>[] = [
    {
      key: "record",
      header: "Record",
      value: (row) => `${row.title} ${row.id}`,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <Link to={`/projects/${row.projectId}?tab=${row.tab}`} className="font-medium text-ink hover:text-accent">{row.title}</Link>
          <p className="text-meta text-ink-muted">{row.kind} · {row.id} · {row.projectId}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
    },
    {
      key: "due",
      header: "Due",
      align: "right",
      value: (row) => row.due ?? "",
      cell: (row) => formatDate(row.due),
    },
  ];

  return (
    <>
      <PageHeader
        title="My Work"
        description="Tasks you own, with anything blocked or overdue brought to the front."
        scope={projects.find(project=>project.project_id===projectId)?.project_name ?? "Your work across accessible projects"}
        actions={<><Button disabled={tasks.isFetching} onClick={() => void tasks.refetch()}>Refresh tasks</Button><Link to={projectId ? `/calendar?project=${encodeURIComponent(projectId)}` : "/calendar"}><Button>Open calendar</Button></Link></>}
      />

      <FilterBar active={Boolean(projectId||params.get("view"))} onClear={()=>clear(["project","view"])} description="Personal work view" shareable={false}>
        <Field label="Project" htmlFor="work-project">
        <Select
          id="work-project"
          value={projectId}
          onChange={(event) => update({project:event.target.value})}
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.project_name}
            </option>
          ))}
        </Select>
        </Field>
        <Field label="Focus" htmlFor="work-focus"><Select id="work-focus" value={view} onChange={e=>update({view:e.target.value==="all"?undefined:e.target.value})}><option value="all">All my work</option><option value="blocked">Blocked</option><option value="overdue">Overdue</option><option value="upcoming">Upcoming · 14 days</option><option value="completed">Completed</option></Select></Field>
      </FilterBar>

      {notice ? <p role="status" className="mb-4 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
      <p className="mb-3 text-meta text-ink-secondary">Your work refreshes automatically while this page is open. Completion is recorded with your account in the audit trail.</p>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <MetricCard label="Blocked" value={counted(blocked.length, blockedActions.length)} caption="Tasks and actions waiting on something else" onClick={()=>update({view:view==="blocked"?undefined:"blocked"})} active={view==="blocked"}/>
        <MetricCard label="Overdue" value={counted(overdue.length, overdueActions.length)} caption="Due date already passed" onClick={()=>update({view:view==="overdue"?undefined:"overdue"})} active={view==="overdue"}/>
        <MetricCard label="Due within 14 days" value={counted(dueSoon.length, dueSoonActions.length)} caption="Tasks and actions coming up next" onClick={()=>update({view:view==="upcoming"?undefined:"upcoming"})} active={view==="upcoming"}/>
        <MetricCard label="Completed" value={counted(completed.length, completedActions.length)} caption="Accepted work; anything awaiting review is not counted" onClick={() => update({ view: view === "completed" ? undefined : "completed" })} active={view === "completed"} />
      </div>

      <div className="mt-4">
        <DataTable
          rows={visible}
          label="My work"
          columns={columns}
          rowKey={(row) => row.task_id}
          isLoading={tasks.isLoading}
          error={tasks.isError ? tasks.error : undefined}
          onRetry={() => void tasks.refetch()}
          searchPlaceholder="Filter tasks"
          initialSortKey="due"
          emptyTitle="No work assigned"
          emptyDescription="Tasks assigned to you appear here as soon as they are recorded against a project."
        />
      </div>

      <Section title="My actions" description="Follow-up actions assigned to your account.">
        <DataTable
          rows={actions.data ? visibleActions : undefined}
          label="My actions"
          columns={actionColumns}
          rowKey={(row) => row.action_id}
          isLoading={actions.isLoading}
          error={actions.isError ? actions.error : undefined}
          onRetry={() => void actions.refetch()}
          searchPlaceholder="Filter actions"
          initialSortKey="due"
          emptyTitle="No actions assigned"
          emptyDescription="Actions assigned to your account appear here with their due date."
        />
      </Section>
      <Section title="Other records you own" description="Open risks you mitigate, issues you own and assumptions you are validating.">
        <DataTable
          rows={risks.data && issues.data && assumptions.data ? owned : undefined}
          label="Other records you own"
          columns={ownedColumns}
          rowKey={(row) => `${row.kind}-${row.id}`}
          isLoading={risks.isLoading || issues.isLoading || assumptions.isLoading}
          searchPlaceholder="Filter records"
          initialSortKey="due"
          emptyTitle="Nothing else assigned to you"
          emptyDescription="Risks, issues and assumptions that name your account as owner appear here."
        />
      </Section>
      {editing ? <TaskEditor key={editing.task_id} task={editing} onClose={() => setEditing(null)} onSaved={() => setNotice("Progress saved. Your manager can see the updated task.")} /> : null}
    </>
  );
}
