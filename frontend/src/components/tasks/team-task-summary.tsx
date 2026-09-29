import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Field, Select } from "@/components/ui/form";
import { RecordReference } from "@/components/ui/record-reference";
import { MetricCard } from "@/components/ui/metric-card";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { formatDate } from "@/lib/format";
import { useTaskRegister } from "@/lib/queries";
import { REVIEW_PENDING, isTaskClosed, isTaskComplete } from "@/lib/task-state";
import type { Task } from "@/types/api";

export function TeamTaskSummary({ projectId }: { projectId?: string }): JSX.Element {
  const tasks = useTaskRegister(projectId);
  const [view, setView] = useState("all");
  const all = tasks.data ?? [];
  const unassigned = all.filter(task => task.owner_user_id === null && !isTaskClosed(task));
  const inProgress = all.filter(task => task.status === "In Progress");
  const blocked = all.filter(task => (task.is_blocked || task.status === "Blocked") && !isTaskClosed(task));
  const awaitingReview = all.filter(task => task.review_status === REVIEW_PENDING);
  // Reported completion waiting for a manager is not yet accepted, so it is counted separately.
  const completed = all.filter(task => isTaskComplete(task) && task.review_status !== REVIEW_PENDING);
  const selected = view === "unassigned" ? unassigned : view === "progress" ? inProgress : view === "blocked" ? blocked : view === "review" ? awaitingReview : view === "completed" ? completed : all;
  const columns: Column<Task>[] = [
    { key: "task", header: "Task", value: task => `${task.task_name} ${task.task_id} ${task.project_id}`, cell: task => <div><Link className="font-medium text-accent hover:underline" to={`/projects/${task.project_id}?tab=work&task=${encodeURIComponent(task.task_id)}`}>{task.task_name}</Link><p className="text-meta text-ink-secondary">{task.project_id}</p><RecordReference references={[task.task_id]} /></div> },
    { key: "owner", header: "Assigned to", value: task => task.owner ?? "", cell: task => <div>{task.owner ?? "Unassigned"}{task.owner && task.owner_user_id === null ? <p className="text-meta text-warn">No linked account</p> : null}</div> },
    { key: "state", header: "Status", value: task => task.status, cell: task => <div className="flex flex-wrap items-center gap-1.5"><StatusBadge label={task.status} tone={statusTone(task.status)} />{task.review_status === REVIEW_PENDING ? <StatusBadge label="Awaiting review" tone="warn" /> : null}</div> },
    { key: "progress", header: "Progress", align: "right", value: task => task.completion_percent, cell: task => <span data-numeric>{task.completion_percent}%</span> },
    { key: "updated", header: "Last reported", value: task => task.last_updated_date ?? "", cell: task => formatDate(task.last_updated_date) },
  ];
  const metrics = [
    { key: "unassigned", label: "Unassigned tasks", count: unassigned.length },
    { key: "progress", label: "In progress", count: inProgress.length },
    { key: "blocked", label: "Blocked tasks", count: blocked.length },
    { key: "review", label: "Awaiting review", count: awaitingReview.length },
    { key: "completed", label: "Completed tasks", count: completed.length },
  ];

  return <Card>
    <CardHeader title="Team task progress" description="Saved task updates from the projects you can access."
      action={<Button size="sm" disabled={tasks.isFetching} onClick={() => void tasks.refetch()}>Refresh team tasks</Button>} />
    <CardBody className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">{metrics.map(metric => <MetricCard key={metric.key} label={metric.label}
        value={tasks.data ? metric.count : "—"} active={view === metric.key} onClick={() => setView(view === metric.key ? "all" : metric.key)} />)}</div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Field label="Task status" htmlFor={projectId ? `team-task-state-${projectId}` : "team-task-state"}><Select id={projectId ? `team-task-state-${projectId}` : "team-task-state"} value={view} onChange={event => setView(event.target.value)}><option value="all">All tasks</option><option value="unassigned">Unassigned</option><option value="progress">In progress</option><option value="blocked">Blocked</option><option value="review">Awaiting review</option><option value="completed">Completed</option></Select></Field>
        <Link className="text-body font-medium text-accent hover:underline" to={projectId ? `/projects/${projectId}?tab=work` : "/projects"}>{projectId ? "Create or assign a task" : "Open a project to create or assign tasks"}</Link>
      </div>
      <DataTable label="Team tasks" rows={tasks.data ? selected : undefined} columns={columns} rowKey={task => task.task_id} pageSize={5}
        initialSortKey="updated" initialSortDirection="desc" isLoading={tasks.isLoading} error={tasks.error} onRetry={() => void tasks.refetch()}
        searchPlaceholder="Find a task or person" emptyTitle={all.length ? "No tasks in this view" : "No tasks created yet"}
        emptyDescription={all.length ? "Choose another status to review the rest of the team's work." : "Add a project member and create a task in Delivery plan. Completed work will remain visible here."} />
      <p className="text-meta text-ink-secondary">Refreshes every 30 seconds while visible. Completed counts accepted work only; work reported complete that needs a manager's review is shown under Awaiting review. The audit trail records who completed or reopened a task. Completing a task does not approve a milestone or release.</p>
    </CardBody>
  </Card>;
}
