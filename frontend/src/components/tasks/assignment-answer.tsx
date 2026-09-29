import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, TextArea } from "@/components/ui/form";
import { useAuth } from "@/lib/auth";
import { useRespondToAssignment } from "@/lib/queries";
import type { Task } from "@/types/api";

/** The assignee accepts new work, or declines it with a reason so it can be reassigned. */
export function AssignmentAnswer({ task }: { task: Task }): JSX.Element | null {
  const { user } = useAuth();
  const respond = useRespondToAssignment();
  const [declining, setDeclining] = useState(false);
  const [note, setNote] = useState("");
  if (task.assignment_status !== "Pending" || user?.id == null || task.owner_user_id !== user.id) return null;

  async function answer(decision: "accept" | "decline"): Promise<void> {
    try {
      await respond.mutateAsync({ task, decision, note: decision === "decline" ? note.trim() : undefined });
      setDeclining(false);
    } catch {
      // The refusal stays on screen beside the answer.
    }
  }

  return <>
    <Button size="sm" variant="primary" disabled={respond.isPending || task.row_version == null} onClick={() => void answer("accept")}>
      Accept
    </Button>
    <Button size="sm" disabled={respond.isPending || task.row_version == null} onClick={() => { respond.reset(); setNote(""); setDeclining(true); }}>
      Decline
    </Button>
    {respond.isError && !declining ? <p role="alert" className="w-full text-meta text-critical">{respond.error.message}</p> : null}
    <Drawer open={declining} onClose={() => setDeclining(false)} busy={respond.isPending} dirty={note.trim() !== ""}
      title="Decline this assignment?" description={task.task_name}
      footer={close => <>
        <Button onClick={close}>Cancel</Button>
        <Button variant="danger" disabled={respond.isPending || !note.trim()} onClick={() => void answer("decline")}>
          {respond.isPending ? "Sending" : "Decline assignment"}
        </Button>
      </>}>
      <p className="text-body text-ink-secondary">The task returns to the project's managers with your reason, so it can be reassigned.</p>
      <div className="mt-4">
        <Field label="Why you are declining" htmlFor={`decline-${task.task_id}`} required
          hint="For example leave, a conflicting priority, or missing skills or equipment.">
          <TextArea id={`decline-${task.task_id}`} rows={3} maxLength={1000} value={note} onChange={event => setNote(event.target.value)} />
        </Field>
      </div>
      {respond.isError ? <p className="mt-3 text-body text-critical" role="alert">{respond.error.message}</p> : null}
    </Drawer>
  </>;
}
