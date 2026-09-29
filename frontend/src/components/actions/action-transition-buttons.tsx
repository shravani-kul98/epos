import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, TextArea } from "@/components/ui/form";
import { useTransitionAction } from "@/lib/queries";
import type { Action, ActionStatus } from "@/types/api";

interface Move {
  target: ActionStatus;
  label: string;
  title: string;
  from: readonly string[];
}

// Mirrors the lifecycle the API enforces so only accepted moves are offered; the API still decides.
const MOVES: readonly Move[] = [
  { target: "In Progress", label: "Start", title: "Start this action", from: ["Open", "Blocked"] },
  { target: "Blocked", label: "Mark blocked", title: "Mark this action blocked", from: ["Open", "In Progress"] },
  { target: "Complete", label: "Complete", title: "Complete this action", from: ["In Progress"] },
];

/** The next steps an assignee can record on their own action, each with a short reason. */
export function ActionTransitionButtons({ action }: { action: Action }): JSX.Element {
  const transition = useTransitionAction();
  const [move, setMove] = useState<Move | null>(null);
  const [reason, setReason] = useState("");
  const available = MOVES.filter(item => item.from.includes(action.status));
  const reasonId = `action-reason-${action.action_id}`;
  const trimmed = reason.trim();

  async function confirm(): Promise<void> {
    if (!move || !trimmed) return;
    try {
      await transition.mutateAsync({ action, target: move.target, rationale: trimmed });
      setMove(null);
    } catch {
      // The panel keeps the reason and shows why the change was refused.
    }
  }

  if (available.length === 0) return <span className="text-meta text-ink-secondary">No further steps</span>;

  return <>
    {available.map(item => <Button key={item.target} size="sm" disabled={action.row_version == null}
      aria-label={`${item.label} ${action.action_id}`}
      onClick={() => { transition.reset(); setReason(""); setMove(item); }}>{item.label}</Button>)}
    <Drawer open={move !== null} onClose={() => setMove(null)} busy={transition.isPending} dirty={trimmed !== ""}
      title={move?.title ?? "Update action"} description={action.action_description}
      footer={close => <><Button onClick={close}>Cancel</Button><Button variant="primary" disabled={transition.isPending || !trimmed} onClick={() => void confirm()}>{transition.isPending ? "Saving" : "Confirm"}</Button></>}>
      {move ? <div className="space-y-4">
        <p className="text-body text-ink-secondary">{action.action_id} moves from {action.status} to {move.target}.</p>
        <Field label="Reason" htmlFor={reasonId} hint="Required. Kept with the change in the audit trail.">
          <TextArea id={reasonId} rows={3} maxLength={1000} required value={reason} onChange={event => setReason(event.target.value)} />
        </Field>
        {transition.isError ? <p role="alert" className="text-body text-critical">{transition.error.message}</p> : null}
      </div> : null}
    </Drawer>
  </>;
}
