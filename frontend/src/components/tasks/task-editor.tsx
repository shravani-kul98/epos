import { useId, useState } from "react";
import { isStaleVersion } from "@/components/governance/lifecycle-section";
import { AssigneeField } from "@/components/tasks/assignee-field";
import { TaskProgressHistory } from "@/components/tasks/task-progress-history";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { RecordReference } from "@/components/ui/record-reference";
import { ApiError, useAuth } from "@/lib/auth";
import { useUpdateTask } from "@/lib/queries";
import type { Task } from "@/types/api";

const STATUSES = ["Not Started", "In Progress", "Blocked", "Complete", "Cancelled"];

export function TaskEditor({ task, onClose, onSaved }: { task: Task; onClose: () => void; onSaved?: (task: Task) => void }): JSX.Element {
  const { can } = useAuth();
  const canManage = can("work.manage");
  const formId = useId();
  const [draft, setDraft] = useState<Partial<Task>>({});
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState<string | undefined>();
  const updateTask = useUpdateTask(task.project_id);
  const fieldErrors = updateTask.error instanceof ApiError ? updateTask.error.fieldErrors : {};
  const status = draft.status ?? task.status;
  const reviewRequired = draft.review_required ?? Boolean(task.review_required);
  // Only managers cancel work, and review-required work is submitted with "Submit for review".
  const offered = STATUSES.filter(value =>
    (canManage || value !== "Cancelled") && (canManage || !reviewRequired || value !== "Complete"));
  const statuses = offered.includes(task.status) ? offered : [task.status, ...offered];
  const dirty = note.trim() !== "" || Object.entries(draft).some(([key, value]) => value !== task[key as keyof Task]);
  const becomingBlocked = status === "Blocked" && task.status !== "Blocked" && !task.is_blocked;

  function setReviewRequired(checked: boolean): void {
    setDraft(current => {
      const next = { ...current };
      if (checked === Boolean(task.review_required)) delete next.review_required;
      else next.review_required = checked;
      return next;
    });
  }

  async function save(): Promise<void> {
    if (task.row_version == null) return;
    setNoteError(undefined);
    const progressNote = note.trim();
    if (becomingBlocked && !progressNote) {
      setNoteError("Say what is blocking the task so the right person can clear it.");
      return;
    }
    try {
      const saved = await updateTask.mutateAsync({
        taskId: task.task_id,
        patch: { ...draft, ...(progressNote ? { progress_note: progressNote } : {}), row_version: task.row_version },
      });
      onSaved?.(saved);
      onClose();
    } catch {
      // A failed save must keep the draft available for correction.
    }
  }

  return <Drawer open onClose={onClose} title={canManage ? "Edit / assign task" : "Update my task"}
    description={task.task_name} dirty={dirty} busy={updateTask.isPending}
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={updateTask.isPending || !dirty || task.row_version == null}>{updateTask.isPending ? "Saving" : "Save changes"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <RecordReference references={[task.task_id, task.milestone_id]} />
      {canManage ? <>
        <Field label="Task name" htmlFor="edit-task-name" error={fieldErrors.task_name}><TextInput id="edit-task-name" required maxLength={200} value={draft.task_name ?? task.task_name} onChange={event => setDraft(current => ({ ...current, task_name: event.target.value }))} /></Field>
        <AssigneeField projectId={task.project_id} value={draft.owner_user_id === undefined ? task.owner_user_id : draft.owner_user_id}
          currentName={task.owner} legacyUnchanged={Boolean(task.owner && task.owner_user_id === null && draft.owner_user_id === undefined)}
          error={fieldErrors.owner_user_id} onChange={owner_user_id => setDraft(current => ({ ...current, owner_user_id }))} />
        <Field label="Forecast end date" htmlFor="task-forecast" error={fieldErrors.forecast_end_date}><TextInput id="task-forecast" type="date" required value={draft.forecast_end_date ?? task.forecast_end_date} onChange={event => setDraft(current => ({ ...current, forecast_end_date: event.target.value }))} /></Field>
        <div className="flex items-start gap-2.5">
          <input id="task-review-required" type="checkbox" className="mt-1 h-4 w-4 shrink-0 accent-accent" checked={reviewRequired}
            aria-describedby="task-review-required-hint" onChange={event => setReviewRequired(event.target.checked)} />
          <div>
            <label htmlFor="task-review-required" className="text-body font-medium text-ink">Requires manager review</label>
            <p id="task-review-required-hint" className="text-meta text-ink-secondary">When the assignee completes it, a manager accepts the work or returns it with a note.</p>
          </div>
        </div>
      </> : null}
      <Field label="Status" htmlFor="task-status" error={fieldErrors.status}><Select id="task-status" value={status} onChange={event => setDraft(current => ({ ...current, status: event.target.value }))}>{statuses.map(value => <option key={value}>{value}</option>)}</Select></Field>
      {status === "Complete" ? <p className="text-body text-ink-secondary">Saving Complete records 100% progress and clears the blocker flag.</p> : <Field label="Completion" htmlFor="task-progress" error={fieldErrors.completion_percent} hint="Whole percentage from 0 to 100. Reopening resets progress unless you set a new value.">
        <TextInput id="task-progress" type="number" min={0} max={100} step={1} required
          value={draft.completion_percent ?? task.completion_percent} onChange={event => setDraft(current => ({ ...current, completion_percent: Number(event.target.value) }))} />
      </Field>}
      <Field label={becomingBlocked ? "What is blocking the task" : "Progress note"} htmlFor="task-note" error={noteError ?? fieldErrors.progress_note}
        required={becomingBlocked}
        hint={becomingBlocked
          ? "Required when you mark the task Blocked, so the right person can clear it."
          : "Optional. What you did, what comes next, or what is in your way. It is kept in the task history below."}>
        <TextArea id="task-note" rows={3} maxLength={1000} value={note} onChange={event => { setNote(event.target.value); setNoteError(undefined); }} />
      </Field>
      <p className="text-meta text-ink-secondary">{reviewRequired && !canManage
        ? "This task needs manager review: use Submit for review when the work is done. Choose Blocked when you cannot proceed."
        : "Choose Blocked when you cannot proceed. Choose In Progress to record that work can continue. Changes are recorded in the audit trail."}</p>
      {updateTask.isError ? <div role="alert" className="text-body text-critical"><p>{updateTask.error.message}</p>{isStaleVersion(updateTask.error) ? <p className="mt-2">Close this panel and reopen the task to review the latest version before saving again.</p> : null}</div> : null}
    </form>
    <TaskProgressHistory taskId={task.task_id} />
  </Drawer>;
}
