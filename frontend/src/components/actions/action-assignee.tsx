import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { useAuth } from "@/lib/auth";
import { useAssignAction, useTaskAssignees } from "@/lib/queries";
import type { Action } from "@/types/api";

/** Link an action to a member's account, so it reaches their My Work and Inbox. */
export function ActionAssignee({ action, onAssigned }: {
  action: Action;
  onAssigned?: (action: Action) => void;
}): JSX.Element | null {
  const { can } = useAuth();
  // Listing assignable members needs work.manage; changing the action needs action.manage.
  const allowed = can("action.manage") && can("work.manage");
  const people = useTaskAssignees(action.project_id, allowed);
  const assign = useAssignAction();
  const current = action.owner_user_id == null ? "" : String(action.owner_user_id);
  const [choice, setChoice] = useState(current);
  if (!allowed) return null;

  const selectId = `action-assignee-${action.action_id}`;
  const options = Array.isArray(people.data) ? people.data : [];
  const listed = current === "" || options.some(person => String(person.user_id) === current);
  const unchanged = choice === current;

  async function save(): Promise<void> {
    if (unchanged || action.row_version == null) return;
    try {
      const saved = await assign.mutateAsync({ action, ownerUserId: choice ? Number(choice) : null });
      onAssigned?.(saved);
    } catch {
      // The refusal is shown below and the selection stays, so it can be corrected.
    }
  }

  return <div className="space-y-2">
    <Field label="Assigned account" htmlFor={selectId} hint="The person sees this action in My Work and is told in their Inbox.">
      <Select id={selectId} value={choice} disabled={people.isLoading || assign.isPending}
        onChange={event => { assign.reset(); setChoice(event.target.value); }}>
        <option value="">Not linked to an account</option>
        {!listed ? <option value={current} disabled>{action.owner ?? "Linked account"} (no longer assignable)</option> : null}
        {options.map(person => <option key={person.user_id} value={String(person.user_id)}>{person.full_name} · {person.role_label}</option>)}
      </Select>
    </Field>
    {people.isError ? <p role="alert" className="text-meta text-critical">{people.error.message}</p> : null}
    <div className="flex items-center gap-3">
      <Button size="sm" variant="primary" disabled={unchanged || assign.isPending || action.row_version == null} onClick={() => void save()}>
        {assign.isPending ? "Saving" : "Save assignment"}
      </Button>
      {assign.isSuccess && unchanged ? <span role="status" className="text-meta text-ok">Assignment saved</span> : null}
    </div>
    {assign.isError ? <p role="alert" className="text-meta text-critical">{assign.error.message}</p> : null}
  </div>;
}
