import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { MilestoneTimeline } from "@/components/charts/milestone-timeline";
import { DeliveryTimeline } from "@/components/charts/delivery-timeline";
import { DependencyHandoffs } from "@/components/charts/dependency-handoffs";
import { DependencyFormDrawer } from "@/components/governance/dependency-form-drawer";
import { CompleteTaskButton } from "@/components/tasks/complete-task-button";
import { CreateWorkDrawer } from "@/components/tasks/create-work-drawer";
import { TaskEditor } from "@/components/tasks/task-editor";
import { TaskReviewActions, TaskReviewBadge } from "@/components/tasks/task-review-actions";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { RecordReference } from "@/components/ui/record-reference";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { daysUntil, formatDate } from "@/lib/format";
import { useDependencies, useMilestones, useTasks } from "@/lib/queries";
import { isTaskClosed } from "@/lib/task-state";
import { useViewParams } from "@/lib/view-params";
import type { Task } from "@/types/api";

export function WorkTab({ projectId, asOfDate, projectStart }: { projectId: string; asOfDate: string; projectStart?: string | null }): JSX.Element {
  const { user, can } = useAuth();
  const milestones = useMilestones(projectId);
  const tasks = useTasks(projectId);
  const dependencies = useDependencies();
  const [editing, setEditing] = useState<Task | null>(null);
  const [creating, setCreating] = useState<"task" | "milestone" | null>(null);
  const [addingDependency, setAddingDependency] = useState(false);
  const [notice, setNotice] = useState("");
  const { params, update } = useViewParams();
  const showTimeline = params.get("view") !== "records";
  const blockedOnly = params.get("state") === "blocked";

  const editable = can("work.update");
  const canManage = can("work.manage");
  const recordNames = Object.fromEntries([
    ...(milestones.data ?? []).map(milestone => [milestone.milestone_id, milestone.milestone_name] as const),
    ...(tasks.data ?? []).map(task => [task.task_id, task.task_name] as const),
  ]);

  useEffect(() => {
    const task = tasks.data?.find(row => row.task_id === params.get("task"));
    if (task && editable && (canManage || task.owner_user_id === user?.id)) {
      setEditing(current => current?.task_id === task.task_id ? current : task);
    }
  }, [params, tasks.data, editable, canManage, user?.id]);

  function openEditor(task: Task): void {
    if (!canManage && task.owner_user_id !== user?.id) return;
    setEditing(task);
  }

  function closeEditor(): void {
    setEditing(null);
    update({ task: undefined });
  }

  const columns: Column<Task>[] = [
    {
      key: "task",
      header: "Task",
      value: (row) => row.task_name,
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.task_name}</p>
          <p className="text-meta text-ink-secondary">{milestones.data?.find(milestone => milestone.milestone_id === row.milestone_id)?.milestone_name ?? "Delivery checkpoint"}</p>
          <RecordReference references={[row.task_id, row.milestone_id]} />
        </div>
      ),
    },
    { key: "owner", header: "Assigned to", value: (row) => row.owner ?? "", cell: (row) => <div>{row.owner ?? "Unassigned"}{row.owner && row.owner_user_id === null ? <p className="text-meta text-warn">Not linked to an account</p> : null}</div> },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge label={row.status} tone={statusTone(row.status)} />
          {row.is_blocked ? <StatusBadge label="Blocked" tone="critical" /> : null}
          <TaskReviewBadge status={row.review_status} />
        </div>
      ),
    },
    {
      key: "progress",
      header: "Progress",
      align: "right",
      value: (row) => row.completion_percent,
      cell: (row) => (
        <div className="flex items-center justify-end gap-2">
          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-subtle">
            <div
              className={cn("h-full rounded-full", row.completion_percent >= 100 ? "bg-ok" : "bg-accent")}
              style={{ width: `${row.completion_percent}%` }}
              role="presentation"
            />
          </div>
          <span className="w-9 text-right" data-numeric>
            {row.completion_percent}%
          </span>
        </div>
      ),
    },
    {
      key: "forecast",
      header: "Forecast end",
      align: "right",
      value: (row) => row.forecast_end_date,
      cell: (row) => {
        const remaining = daysUntil(row.forecast_end_date, asOfDate);
        const overdue = remaining !== null && remaining < 0 && !isTaskClosed(row);
        return (
          <span className={cn(overdue && "font-medium text-critical")} data-numeric>
            {formatDate(row.forecast_end_date)}
            {overdue ? ` · ${Math.abs(remaining)}d late` : ""}
          </span>
        );
      },
    },
    {
      key: "updated",
      header: "Last update",
      align: "right",
      value: (row) => row.last_updated_date ?? "",
      cell: (row) => formatDate(row.last_updated_date),
    },
    {
      key: "actions", header: "Actions",
      cell: task => editable && (canManage || task.owner_user_id === user?.id) ? <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => openEditor(task)}>{canManage ? "Edit / assign" : "Update progress"}</Button>
        <CompleteTaskButton task={task} />
        <TaskReviewActions task={task} />
      </div> : <span className="text-meta text-ink-secondary">Read only</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Delivery view" className="flex gap-2"><Button aria-pressed={showTimeline} variant={showTimeline?"primary":"secondary"} onClick={()=>update({view:undefined})}>Timeline</Button><Button aria-pressed={!showTimeline} variant={!showTimeline?"primary":"secondary"} onClick={()=>update({view:"records"})}>Records</Button></div>
        <div className="flex flex-wrap gap-2">
          <Button aria-pressed={blockedOnly} onClick={()=>update({state:blockedOnly?undefined:"blocked"})}>{blockedOnly?"Show all work":"Show blocked work"}</Button>
          {canManage ? <><Button onClick={() => setAddingDependency(true)}>Add dependency</Button><Button onClick={() => setCreating("milestone")}>New milestone</Button><Button variant="primary" onClick={() => setCreating("task")}>New task</Button></> : null}
        </div>
      </div>
      {can("project_members.manage") ? <Link className="inline-block text-body font-medium text-accent hover:underline" to={`/projects/${projectId}?tab=members`}>Manage team members and project access</Link> : null}
      {notice ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
      {showTimeline ? <Card><CardHeader title="Delivery plan" description="Planned, baseline, forecast and actual dates on a common time scale" /><CardBody>
        {milestones.isError || tasks.isError ? <ErrorState error={milestones.error ?? tasks.error} onRetry={()=>{void milestones.refetch();void tasks.refetch();}} /> : milestones.isLoading || tasks.isLoading ? <SkeletonTable rows={5}/> : <DeliveryTimeline milestones={milestones.data ?? []} tasks={(tasks.data ?? []).filter(task=>!blockedOnly || task.is_blocked)} asOfDate={asOfDate} projectStart={projectStart} />}
      </CardBody></Card> : (
      <Card>
        <CardHeader title="Milestones" description="Baseline against forecast, from the stored dates" />
        {milestones.isError ? <ErrorState error={milestones.error} onRetry={()=>void milestones.refetch()}/> : milestones.isLoading ? (
          <SkeletonTable rows={4} />
        ) : !milestones.data || milestones.data.length === 0 ? (
          <EmptyState
            title="No milestones recorded"
            description="Milestone dates drive the schedule and readiness factors of the health score."
            className="py-8"
          />
        ) : (
          <CardBody>
            <MilestoneTimeline milestones={milestones.data} asOfDate={asOfDate} />
          </CardBody>
        )}
      </Card>
      )}

      <details className="disclosure"><summary>Dependency hand-offs</summary><div className="p-4">{dependencies.isError ? <ErrorState error={dependencies.error} onRetry={()=>void dependencies.refetch()}/> : dependencies.isLoading ? <SkeletonTable rows={2}/> : <DependencyHandoffs dependencies={(dependencies.data??[]).filter(dependency=>dependency.project_id===projectId)} names={recordNames}/>}</div></details>

      <h2 className="text-section font-semibold">Delivery tasks</h2>
      <DataTable
        rows={tasks.data?.filter(task=>!blockedOnly || task.is_blocked)}
        label="Delivery tasks"
        columns={columns}
        rowKey={(row) => row.task_id}
        isLoading={tasks.isLoading}
        error={tasks.isError ? tasks.error : undefined}
        onRetry={() => void tasks.refetch()}
        onRowClick={editable ? openEditor : undefined}
        canOpenRow={task=>canManage || task.owner_user_id===user?.id}
        searchPlaceholder="Filter tasks"
        emptyTitle={blockedOnly && (tasks.data?.length ?? 0) > 0 ? "Nothing is blocked" : "No tasks recorded"}
        emptyDescription={blockedOnly && (tasks.data?.length ?? 0) > 0
          ? "No task in this project is marked blocked. Show all work to see the rest of the plan."
          : canManage ? "Create the first task, choose its assignee, and set a due date." : "Tasks will appear here when your project manager creates them."}
        emptyAction={blockedOnly && (tasks.data?.length ?? 0) > 0
          ? <Button onClick={() => update({ state: undefined })}>Show all work</Button>
          : canManage ? <Button variant="primary" onClick={() => setCreating("task")}>Create the first task</Button> : undefined}
        toolbar={
          <Button size="sm" disabled={tasks.isFetching} onClick={() => void tasks.refetch()}>Refresh tasks</Button>
        }
      />

      {editing ? <TaskEditor key={editing.task_id} task={editing} onClose={closeEditor} onSaved={() => setNotice("Task saved. The assignee's work list and manager views will reflect this update.")} /> : null}
      {creating ? <CreateWorkDrawer key={creating} projectId={projectId} kind={creating} onClose={() => setCreating(null)} onNeedMilestone={() => setCreating("milestone")} onCreated={message => { setNotice(message); update({ state: undefined }); }} /> : null}
      {addingDependency ? <DependencyFormDrawer projectId={projectId} onClose={() => setAddingDependency(false)}
        onSaved={dependency => setNotice(`Dependency ${dependency.dependency_id} added. It now feeds dependency health and scenario analysis.`)} /> : null}
    </div>
  );
}
