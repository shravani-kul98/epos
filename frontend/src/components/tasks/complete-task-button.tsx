import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, TextArea } from "@/components/ui/form";
import { useAuth } from "@/lib/auth";
import { useCompleteTask } from "@/lib/queries";
import { isTaskClosed } from "@/lib/task-state";
import type { Task } from "@/types/api";

export function CompleteTaskButton({ task }: { task: Task }): JSX.Element | null {
  const { user, can } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [note, setNote] = useState("");
  const complete = useCompleteTask();
  const forReview = task.review_required;
  if (!can("work.update") || (!can("work.manage") && task.owner_user_id !== user?.id)) return null;
  // Review-required work is submitted by its assignee; managers accept it through the review.
  if (forReview && task.owner_user_id !== user?.id) return null;
  if (isTaskClosed(task)) return complete.isSuccess ? <span role="status" className="text-meta font-medium text-ok">{forReview ? "Submitted for review" : "Completion recorded"}</span> : null;

  async function confirm(): Promise<void> {
    try {
      await complete.mutateAsync({ task, note: note.trim() || undefined });
      setConfirming(false);
    } catch {
      // The mutation retains the error and leaves the confirmation open.
    }
  }

  return <>
    <Button size="sm" disabled={task.row_version == null} onClick={() => { complete.reset(); setNote(""); setConfirming(true); }}>
      <Check size={14} aria-hidden="true" />{forReview ? "Submit for review" : "Mark complete"}
    </Button>
    <Drawer open={confirming} onClose={() => setConfirming(false)} busy={complete.isPending} dirty={note.trim() !== ""}
      title={forReview ? "Submit this task for review?" : "Complete this task?"} description={task.task_name}
      footer={close => <><Button onClick={close}>Cancel</Button><Button variant="primary" disabled={complete.isPending} onClick={() => void confirm()}>{complete.isPending ? "Saving" : forReview ? "Confirm submission" : "Confirm completion"}</Button></>}>
      <p className="text-body text-ink-secondary">{forReview
        ? "This records your completion, sets progress to 100%, and clears the blocker flag. Your manager will review the work and accept it or return it to you with a note."
        : "This records your completion, sets progress to 100%, and clears the blocker flag. Your manager will see the updated task and who completed it."}</p>
      <div className="mt-4">
        <Field label="Completion note" htmlFor={`complete-note-${task.task_id}`}
          hint="Optional. What was delivered, where it can be found, or anything left for follow-up.">
          <TextArea id={`complete-note-${task.task_id}`} rows={3} maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
        </Field>
      </div>
      <p className="mt-3 text-meta text-ink-secondary">Actual work dates are not guessed. This records a task update, not an approval of a milestone or release.</p>
      {complete.isError ? <p className="mt-4 text-body text-critical" role="alert">{complete.error.message}</p> : null}
    </Drawer>
  </>;
}
