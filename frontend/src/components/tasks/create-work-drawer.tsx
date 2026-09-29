import { useId, useState } from "react";
import { AssigneeField } from "@/components/tasks/assignee-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, CheckboxField, Select, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useCreateMilestone, useCreateTask, useMilestones, useProjectDashboard } from "@/lib/queries";

export function CreateWorkDrawer({ projectId, kind, onClose, onNeedMilestone, onCreated }: {
  projectId: string;
  kind: "task" | "milestone";
  onClose: () => void;
  onNeedMilestone: () => void;
  onCreated: (message: string) => void;
}): JSX.Element {
  const formId = useId();
  const milestones = useMilestones(projectId);
  const dashboard = useProjectDashboard(kind === "milestone" ? projectId : "");
  const projectEnd = dashboard.data?.project?.forecast_end_date ?? null;
  const createTask = useCreateTask();
  const createMilestone = useCreateMilestone();
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [forecast, setForecast] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [assignee, setAssignee] = useState<number | null>(null);
  const [criticality, setCriticality] = useState("");
  const [reviewRequired, setReviewRequired] = useState(false);
  const mutation = kind === "task" ? createTask : createMilestone;
  const noMilestones = kind === "task" && !milestones.isLoading && !milestones.isError && milestones.data?.length === 0;
  const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};
  const dirty = Boolean(name || due || forecast || milestoneId || assignee || criticality);

  async function save(): Promise<void> {
    try {
      if (kind === "task") {
        await createTask.mutateAsync({ project_id: projectId, milestone_id: milestoneId, task_name: name.trim(), owner_user_id: assignee, planned_end_date: due, forecast_end_date: forecast, status: "Not Started", completion_percent: 0, ...(reviewRequired ? { review_required: true } : {}) });
        onCreated(assignee === null ? "Task created. Assign it when a responsible person is available." : "Task created and assigned. It is now available in the assignee's My Work.");
      } else {
        await createMilestone.mutateAsync({ project_id: projectId, milestone_name: name.trim(), baseline_date: due, forecast_date: forecast, status: "Not Started", criticality, owner: null });
        onCreated("Milestone created. You can now add tasks against it.");
      }
      onClose();
    } catch {
      // Server validation errors stay with the entered form values.
    }
  }

  return <Drawer open title={kind === "task" ? "New task" : "New milestone"}
    description={kind === "task" ? "Describe the work, choose a person, and set the due date." : "Add the delivery checkpoint your tasks will contribute to."}
    onClose={onClose} dirty={dirty} busy={mutation.isPending}
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={mutation.isPending || noMilestones || (kind === "task" && (milestones.isLoading || milestones.isError))}>{mutation.isPending ? "Saving" : kind === "task" ? "Create task" : "Create milestone"}</Button></>}>
    {noMilestones ? <div className="space-y-3"><p className="text-body text-ink-secondary">This project has no milestones. Add a delivery checkpoint first so the task has a place in the plan.</p><Button variant="primary" onClick={onNeedMilestone}>Add the first milestone</Button></div> : <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label={kind === "task" ? "Task name" : "Milestone name"} htmlFor="new-work-name" error={fieldErrors.task_name ?? fieldErrors.milestone_name}><TextInput id="new-work-name" value={name} onChange={event => setName(event.target.value)} required maxLength={200} /></Field>
      {kind === "task" ? <>
        <Field label="Milestone" htmlFor="new-task-milestone" hint="The delivery checkpoint this task contributes to." error={fieldErrors.milestone_id}><Select id="new-task-milestone" value={milestoneId} required disabled={milestones.isLoading} onChange={event => setMilestoneId(event.target.value)}><option value="">Choose a milestone</option>{(milestones.data ?? []).map(milestone => <option key={milestone.milestone_id} value={milestone.milestone_id}>{milestone.milestone_name}</option>)}</Select></Field>
        {milestones.isError ? <div role="alert"><p className="text-critical">{milestones.error.message}</p><Button onClick={() => void milestones.refetch()}>Retry milestones</Button></div> : null}
        <AssigneeField projectId={projectId} value={assignee} error={fieldErrors.owner_user_id} onChange={setAssignee} />
        <CheckboxField id="new-task-review-required" label="Requires manager review" checked={reviewRequired} onChange={setReviewRequired}
          hint="When the assignee completes it, a manager accepts the work or returns it with a note." />
      </> : <Field label="Criticality" htmlFor="new-milestone-criticality" hint="Choose how important this checkpoint is to delivery."><Select id="new-milestone-criticality" value={criticality} required onChange={event => setCriticality(event.target.value)}><option value="">Choose criticality</option>{["Low", "Medium", "High", "Critical"].map(value => <option key={value}>{value}</option>)}</Select></Field>}
      <Field label={kind === "task" ? "Planned due date" : "Baseline date"} htmlFor="new-work-due" error={fieldErrors.planned_end_date ?? fieldErrors.baseline_date}
        hint={kind === "milestone" ? "The date agreed in the plan." : undefined}><TextInput id="new-work-due" type="date" required value={due} onChange={event => { setDue(event.target.value); if (!forecast || forecast === due) setForecast(event.target.value); }} /></Field>
      <Field label={kind === "task" ? "Expected finish date" : "Forecast date"} htmlFor="new-work-forecast" error={fieldErrors.forecast_end_date ?? fieldErrors.forecast_date}
        hint={kind === "milestone" ? "When it is now expected." : undefined}><TextInput id="new-work-forecast" type="date" required value={forecast} onChange={event => setForecast(event.target.value)} /></Field>
      {kind === "milestone" && projectEnd && forecast && forecast > projectEnd ? (
        <p role="status" className="rounded-control border border-warn bg-warn-tint px-3 py-2 text-meta text-ink">
          This milestone is forecast after the project's own forecast end of {formatDate(projectEnd)}. Move the milestone or update the project forecast so the plan stays consistent.
        </p>
      ) : null}
      {mutation.isError ? <p role="alert" className="text-body text-critical">{mutation.error.message}</p> : null}
    </form>}
  </Drawer>;
}
