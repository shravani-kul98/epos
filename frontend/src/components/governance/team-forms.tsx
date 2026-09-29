import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCreateAction, useCreateResource, useTaskAssignees } from "@/lib/queries";
import type { Action, ResourceAllocation } from "@/types/api";

const PRIORITIES: readonly string[] = ["Critical", "High", "Medium", "Low"];
const WORKING_WEEK_HOURS = 40;

/** Agree a follow-up. With an account chosen, it reaches that person's My Work and Inbox. */
export function ActionFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (action: Action) => void;
}): JSX.Element {
  const formId = useId();
  const { can } = useAuth();
  const linkAccounts = can("work.manage");
  const people = useTaskAssignees(projectId, linkAccounts);
  const create = useCreateAction();
  const [description, setDescription] = useState("");
  const [ownerUserId, setOwnerUserId] = useState("");
  const [ownerName, setOwnerName] = useState<string | null>(null);
  const [due, setDue] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [source, setSource] = useState("");
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const dirty = Boolean(description || ownerUserId || ownerName || due || source);
  const canSave = Boolean(description.trim() && due) && !create.isPending;

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      const action = await create.mutateAsync({
        project_id: projectId,
        action_description: description.trim(),
        owner: linkAccounts ? null : ownerName,
        owner_user_id: linkAccounts && ownerUserId ? Number(ownerUserId) : null,
        due_date: due,
        priority,
        source_reference: source.trim() || null,
      });
      onSaved?.(action);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="New action"
    description="A follow-up agreed in a review or meeting. Actions feed the follow-through factor."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{create.isPending ? "Saving" : "Create action"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Action" htmlFor={`${formId}-description`} error={fieldErrors.action_description} hint="What will be done, stated so its completion is obvious.">
        <TextArea id={`${formId}-description`} rows={3} required maxLength={500} value={description} onChange={event => setDescription(event.target.value)} />
      </Field>
      {linkAccounts ? <Field label="Owner" htmlFor={`${formId}-owner`} error={fieldErrors.owner_user_id}
        hint="The person sees this action in My Work and is told in their Inbox.">
        <Select id={`${formId}-owner`} value={ownerUserId} disabled={people.isLoading || people.isError} onChange={event => setOwnerUserId(event.target.value)}>
          <option value="">{people.isLoading ? "Loading people" : "Unassigned"}</option>
          {(Array.isArray(people.data) ? people.data : []).map(person => <option key={person.user_id} value={String(person.user_id)}>{person.full_name} · {person.role_label}</option>)}
        </Select>
      </Field> : <RecordOwnerField projectId={projectId} purpose="action" label="Owner" id={`${formId}-owner-name`} value={ownerName}
        error={fieldErrors.owner} onChange={setOwnerName} />}
      {people.isError ? <p role="alert" className="text-meta text-critical">{people.error.message}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Due date" htmlFor={`${formId}-due`} error={fieldErrors.due_date}>
          <TextInput id={`${formId}-due`} type="date" required value={due} onChange={event => setDue(event.target.value)} />
        </Field>
        <Field label="Priority" htmlFor={`${formId}-priority`} error={fieldErrors.priority}>
          <Select id={`${formId}-priority`} value={priority} onChange={event => setPriority(event.target.value)}>
            {PRIORITIES.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Source reference" htmlFor={`${formId}-source`} error={fieldErrors.source_reference}
        hint="Optional. Where it was agreed, for example a review or meeting note.">
        <TextInput id={`${formId}-source`} maxLength={500} value={source} onChange={event => setSource(event.target.value)} />
      </Field>
      <MutationError error={create.error} />
    </form>
  </Drawer>;
}

/** Record one person's allocated and available hours for a week of this project. */
export function AllocationFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (allocation: ResourceAllocation) => void;
}): JSX.Element {
  const formId = useId();
  const people = useTaskAssignees(projectId, true);
  const create = useCreateResource();
  const [person, setPerson] = useState("");
  const [week, setWeek] = useState("");
  const [allocated, setAllocated] = useState("");
  const [capacity, setCapacity] = useState(String(WORKING_WEEK_HOURS));
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const allocatedHours = Number(allocated);
  const capacityHours = Number(capacity);
  const valid = Boolean(person && week) && allocated.trim() !== "" && Number.isInteger(allocatedHours) && allocatedHours >= 0
    && Number.isInteger(capacityHours) && capacityHours > 0;
  const dirty = Boolean(person || week || allocated);

  async function save(): Promise<void> {
    if (!valid || create.isPending) return;
    try {
      const allocation = await create.mutateAsync({
        project_id: projectId,
        resource_name: person,
        allocated_hours: allocatedHours,
        capacity_hours: capacityHours,
        week_start_date: week,
      });
      onSaved?.(allocation);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="Record allocation"
    description="Hours one person is allocated to this project in a week, against the hours they have."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!valid || create.isPending}>{create.isPending ? "Saving" : "Record allocation"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Person" htmlFor={`${formId}-person`} error={fieldErrors.resource_name}>
        <Select id={`${formId}-person`} required value={person} disabled={people.isLoading || people.isError} onChange={event => setPerson(event.target.value)}>
          <option value="">{people.isLoading ? "Loading people" : "Choose a project member"}</option>
          {(Array.isArray(people.data) ? people.data : []).map(member => <option key={member.user_id} value={member.full_name}>{member.full_name} · {member.email}</option>)}
        </Select>
      </Field>
      {people.isError ? <p role="alert" className="text-meta text-critical">{people.error.message}</p> : null}
      <Field label="Week starting" htmlFor={`${formId}-week`} error={fieldErrors.week_start_date} hint="The first working day of the week.">
        <TextInput id={`${formId}-week`} type="date" required value={week} onChange={event => setWeek(event.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Allocated hours" htmlFor={`${formId}-allocated`} error={fieldErrors.allocated_hours}>
          <TextInput id={`${formId}-allocated`} type="number" min={0} max={168} step={1} required value={allocated} onChange={event => setAllocated(event.target.value)} />
        </Field>
        <Field label="Available hours" htmlFor={`${formId}-capacity`} error={fieldErrors.capacity_hours} hint="Usually a working week, less leave.">
          <TextInput id={`${formId}-capacity`} type="number" min={1} max={168} step={1} required value={capacity} onChange={event => setCapacity(event.target.value)} />
        </Field>
      </div>
      {valid && allocatedHours > capacityHours ? <p className="rounded-control border border-warn/25 bg-warn-tint px-3 py-2 text-meta text-warn">
        This allocation exceeds the hours available, so the week will show as over capacity.
      </p> : null}
      <MutationError error={create.error} />
    </form>
  </Drawer>;
}
