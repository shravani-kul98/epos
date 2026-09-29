import { useState } from "react";
import { Check, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, TextArea } from "@/components/ui/form";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime } from "@/lib/format";
import { useDeliverables, useReviewTask, useTaskProgress } from "@/lib/queries";
import { REVIEW_PENDING } from "@/lib/task-state";
import type { Task, TaskReviewDecision, TaskReviewStatus } from "@/types/api";

const REVIEW_TONES: Record<TaskReviewStatus, Tone> = {
  "Pending review": "warn",
  Accepted: "ok",
  Returned: "critical",
};

const COPY: Record<TaskReviewDecision, { title: string; confirm: string; label: string; hint: string }> = {
  accept: {
    title: "Accept this work?",
    confirm: "Confirm acceptance",
    label: "Review note",
    hint: "Optional. The assignee sees this note.",
  },
  return: {
    title: "Return for rework?",
    confirm: "Confirm return",
    label: "What needs to change",
    hint: "Required. The assignee sees this note, and the task goes back to In Progress.",
  },
};

export function TaskReviewBadge({ status }: { status: TaskReviewStatus | null | undefined }): JSX.Element | null {
  if (!status) return null;
  return <StatusBadge label={status === REVIEW_PENDING ? "Awaiting review" : status} tone={REVIEW_TONES[status] ?? "neutral"} />;
}

/** What the reviewer needs to decide: the assignee's own words and the agreed acceptance criteria. */
function ReviewEvidence({ task }: { task: Task }): JSX.Element {
  const history = useTaskProgress(task.task_id);
  const deliverables = useDeliverables(task.deliverable_id ? task.project_id : "");
  const completion = history.data?.find(entry => entry.action === "completed" && entry.note);
  const deliverable = deliverables.data?.find(item => item.deliverable_id === task.deliverable_id);

  return <div className="space-y-4">
    <dl className="grid grid-cols-2 gap-3">
      <div><dt className="text-meta text-ink-secondary">Assigned to</dt><dd className="text-body text-ink">{task.owner ?? "Unassigned"}</dd></div>
      <div><dt className="text-meta text-ink-secondary">Last reported</dt><dd className="text-body text-ink">{formatDate(task.last_updated_date)}</dd></div>
    </dl>
    <section>
      <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">Completion note</h3>
      {history.isLoading ? <p className="mt-1 text-meta text-ink-secondary">Loading the completion note…</p>
        : history.isError ? <p role="alert" className="mt-1 text-meta text-critical">{history.error.message}</p>
        : completion ? <div className="mt-1 rounded-control border border-line bg-surface-subtle px-3 py-2">
          <p className="whitespace-pre-wrap text-body text-ink">{completion.note}</p>
          <p className="mt-1 text-meta text-ink-muted">{completion.actor_name ?? "An unrecorded person"} · {formatDateTime(completion.occurred_at)}</p>
        </div>
        : <p className="mt-1 text-meta text-ink-secondary">No completion note was added.</p>}
    </section>
    {task.deliverable_id ? <section>
      <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">Acceptance criteria · {task.deliverable_id}</h3>
      {deliverables.isLoading ? <p className="mt-1 text-meta text-ink-secondary">Loading the acceptance criteria…</p>
        : deliverables.isError ? <p role="alert" className="mt-1 text-meta text-critical">{deliverables.error.message}</p>
        : deliverable?.acceptance_criteria ? <p className="mt-1 whitespace-pre-wrap text-body text-ink">{deliverable.acceptance_criteria}</p>
        : <p className="mt-1 text-meta text-ink-secondary">No acceptance criteria are recorded for this deliverable.</p>}
    </section> : null}
  </div>;
}

/** A manager's decision on reported completion. The API refuses a review by the task's own assignee. */
export function TaskReviewActions({ task }: { task: Task }): JSX.Element | null {
  const { can } = useAuth();
  const review = useReviewTask();
  const [decision, setDecision] = useState<TaskReviewDecision | null>(null);
  const [note, setNote] = useState("");
  if (!can("work.manage")) return null;
  if (task.review_status !== REVIEW_PENDING) {
    return review.isSuccess ? <span role="status" className="text-meta font-medium text-ok">Review recorded</span> : null;
  }

  const copy = COPY[decision ?? "accept"];
  const trimmed = note.trim();
  const noteId = `review-note-${task.task_id}`;
  const blocked = review.isPending || (decision === "return" && !trimmed);

  function start(next: TaskReviewDecision): void {
    review.reset();
    setNote("");
    setDecision(next);
  }

  async function confirm(): Promise<void> {
    if (!decision || blocked) return;
    try {
      await review.mutateAsync({ task, decision, note: trimmed || undefined });
      setDecision(null);
    } catch {
      // The refusal stays in the panel with the note, so the reviewer can correct it and retry.
    }
  }

  return <>
    <Button size="sm" disabled={task.row_version == null} onClick={() => start("accept")}>
      <Check size={14} aria-hidden="true" />Accept
    </Button>
    <Button size="sm" disabled={task.row_version == null} onClick={() => start("return")}>
      <RotateCcw size={14} aria-hidden="true" />Return for rework
    </Button>
    {/* The drawer is portalled, but React still bubbles its clicks to a clickable table row. */}
    <div className="contents" onClick={event => event.stopPropagation()}>
      <Drawer open={decision !== null} onClose={() => setDecision(null)} busy={review.isPending} dirty={trimmed !== ""}
        title={copy.title} description={task.task_name}
        footer={close => <><Button onClick={close}>Cancel</Button><Button variant={decision === "return" ? "danger" : "primary"} disabled={blocked} onClick={() => void confirm()}>{review.isPending ? "Saving" : copy.confirm}</Button></>}>
        {decision ? <div className="space-y-4">
          <ReviewEvidence task={task} />
          <Field label={copy.label} htmlFor={noteId} hint={copy.hint}>
            <TextArea id={noteId} rows={3} maxLength={1000} required={decision === "return"} value={note} onChange={event => setNote(event.target.value)} />
          </Field>
          {review.isError ? <p role="alert" className="text-body text-critical">{review.error.message}</p> : null}
        </div> : null}
      </Drawer>
    </div>
  </>;
}
