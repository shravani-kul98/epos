import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { useAuth } from "@/lib/auth";
import { useAddProjectMember, useMemberCandidates, useTaskAssignees } from "@/lib/queries";
import { personOptionLabel, sharedNames } from "@/lib/person-label";

interface AssigneeFieldProps {
  projectId: string;
  value: number | null;
  currentName?: string | null;
  legacyUnchanged?: boolean;
  error?: string;
  onChange: (value: number | null) => void;
}

export function AssigneeField({ projectId, value, currentName, legacyUnchanged = false, error, onChange }: AssigneeFieldProps): JSX.Element {
  const { can } = useAuth();
  const people = useTaskAssignees(projectId, can("work.manage"));
  const [adding, setAdding] = useState(false);
  const [candidateId, setCandidateId] = useState("");
  const candidates = useMemberCandidates(projectId, adding && can("project_members.manage"));
  const addMember = useAddProjectMember(projectId);
  const addId = useId();
  const eligible = (role: string): boolean => ["engineer", "engineering_lead", "project_manager", "pmo_analyst", "administrator"].includes(role);
  async function addAndSelect(): Promise<void> {
    if (!candidateId) return;
    try {
      const added = await addMember.mutateAsync({ user_id: Number(candidateId), project_role: "Contributor" });
      await people.refetch();
      onChange(added.user_id);
      setAdding(false);
      setCandidateId("");
    } catch {
      // A refused membership change must not alter the task's draft assignee.
    }
  }
  const missingCurrent = value !== null && !people.data?.some(person => person.user_id === value);
  const shared = sharedNames(people.data ?? []);
  return <div className="space-y-2">
    <Field label="Assigned to" htmlFor="task-assignee" error={error}
      hint="Select a registered project member. Email addresses appear only to tell apart people with the same name.">
      <Select id="task-assignee" value={legacyUnchanged ? "legacy" : value ?? ""}
        aria-busy={people.isLoading}
        disabled={people.isLoading || people.isError}
        onChange={event => onChange(event.target.value ? Number(event.target.value) : null)}>
        <option value="">{people.isLoading ? "Loading people" : "Unassigned"}</option>
        {legacyUnchanged ? <option value="legacy" disabled>{currentName} — not linked to an account</option> : null}
        {missingCurrent ? <option value={value} disabled>{currentName ?? "Recorded assignee"} — unavailable for new assignments</option> : null}
        {(people.data ?? []).map(person => <option key={person.user_id} value={person.user_id}>{personOptionLabel(person, shared)}</option>)}
      </Select>
    </Field>
    <div className="flex flex-wrap gap-2"><Button size="sm" disabled={people.isFetching} onClick={() => void people.refetch()}>Refresh people</Button>
      {can("project_members.manage") ? <Button size="sm" aria-expanded={adding} aria-controls={adding ? addId : undefined} onClick={() => { setAdding(!adding); addMember.reset(); }}>Add another person…</Button> : null}
    </div>
    <p className="text-meta text-ink-secondary">Only this project's active members with task-update permission appear here.</p>
    {adding ? <section id={addId} aria-label="Add a person without leaving this task" className="space-y-3 rounded-control border border-line bg-surface-subtle p-3">
      <Field label="Person to add" htmlFor={`${addId}-person`} hint="Adding them grants project access. The task is assigned only when you save the task form.">
        <Select id={`${addId}-person`} value={candidateId} disabled={candidates.isLoading || candidates.isError || addMember.isPending} onChange={event => setCandidateId(event.target.value)}>
          <option value="">{candidates.isLoading ? "Loading registered accounts" : "Choose an account"}</option>
          {(candidates.data ?? []).map(person => <option key={person.user_id} value={person.user_id} disabled={!eligible(person.workspace_role)}>{person.full_name} · {person.email}{eligible(person.workspace_role) ? "" : " — role cannot update tasks"}</option>)}
        </Select>
      </Field>
      {candidates.data?.length === 0 ? <p className="text-meta text-ink-secondary">No other active accounts are available. The person must register on this EPOS site first.</p> : null}
      {candidates.isError ? <div role="alert"><p>{candidates.error.message}</p><Button onClick={() => void candidates.refetch()}>Retry accounts</Button></div> : null}
      {addMember.isError ? <p role="alert" className="text-meta text-critical">{addMember.error.message}</p> : null}
      <Button disabled={!candidateId || addMember.isPending || candidates.isError} onClick={() => void addAndSelect()}>{addMember.isPending ? "Adding" : "Add to project and select"}</Button>
    </section> : null}
    {people.isError ? <div role="alert" className="text-meta text-critical"><p>{people.error.message}</p><Button size="sm" onClick={() => void people.refetch()}>Retry people</Button></div> : null}
    {!people.isLoading && !people.isError && people.data?.length === 0 ? <p className="text-meta text-ink-secondary">
      {can("project_members.manage") ? "Add a person in the Team members tab before assigning work." : "Ask a Project Manager or PMO Analyst to add an eligible person to this project."}
    </p> : null}
  </div>;
}
