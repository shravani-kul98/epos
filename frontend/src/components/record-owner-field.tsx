import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { useAuth } from "@/lib/auth";
import { useProjectPeople, type RecordOwnerPurpose } from "@/lib/people-queries";
import { personOptionLabel, sharedNames as namesSharedBy } from "@/lib/person-label";

interface RecordOwnerFieldProps {
  projectId: string;
  purpose: RecordOwnerPurpose;
  label: string;
  id: string;
  value: string | null;
  /** The owner's account, for records the API links to a person rather than only a name. */
  userId?: number | null;
  onChange: (name: string | null, userId: number | null) => void;
  required?: boolean;
  error?: string;
  /** True where the API links the chosen account, so the owner is told and sees the record. */
  linksAccount?: boolean;
}

/** Choose a registered project member. A recorded name is never silently linked to someone else. */
export function RecordOwnerField({ projectId, purpose, label, id, value, userId = null, onChange, required = false, error, linksAccount = false }: RecordOwnerFieldProps): JSX.Element {
  const { can } = useAuth();
  const people = useProjectPeople(projectId, purpose);
  const scope = `${projectId}:${purpose}`;
  const [picked, setPicked] = useState<{ userId: number; name: string; scope: string } | null>(null);
  const list = people.data ?? [];
  const named = (accountId: number | null | undefined) =>
    accountId == null ? undefined : list.find(person => person.user_id === accountId && person.full_name === value);
  const sameName = value ? list.filter(person => person.full_name === value) : [];
  const selected = named(userId)
    ?? (picked && picked.scope === scope && picked.name === value ? named(picked.userId) : undefined)
    ?? (sameName.length === 1 ? sameName[0] : undefined);
  const historical = Boolean(value) && !selected;
  const sharedNames = namesSharedBy(list);
  const disabled = !people.canLoad || people.isLoading || people.isError;

  return <div className="space-y-2">
    <Field label={label} htmlFor={id} required={required} error={error}
      hint={linksAccount
        ? "The chosen member is told and sees this record in My Work."
        : "Choose a registered project member. Only the name is saved on this record."}>
      <Select id={id} required={required} value={selected ? String(selected.user_id) : historical ? "historical" : ""}
        aria-busy={people.isFetching} disabled={disabled}
        onChange={event => {
          const person = list.find(item => String(item.user_id) === event.target.value);
          setPicked(person ? { userId: person.user_id, name: person.full_name, scope } : null);
          onChange(person?.full_name ?? null, person?.user_id ?? null);
        }}>
        <option value="">{people.isLoading ? "Loading project members" : required ? "Choose a project member" : "Unassigned"}</option>
        {historical ? <option value="historical" disabled>
          {sameName.length > 1 ? `${value} — recorded name; choose the matching member` : `${value} — recorded name, not a current project member`}
        </option> : null}
        {people.canLoad ? list.map(person => (
          <option key={person.user_id} value={person.user_id}>{personOptionLabel(person, sharedNames)}</option>
        )) : null}
      </Select>
    </Field>
    {people.canLoad ? <Button size="sm" disabled={people.isFetching} onClick={() => void people.refetch()}>
      {people.isError ? "Retry people" : "Refresh people"}
    </Button> : <p className="text-meta text-ink-secondary">Sign in with permission to manage this record to choose a member.</p>}
    {people.canLoad && people.isError ? <p role="alert" className="text-meta text-critical">{people.error.message}</p> : null}
    {people.canLoad && !people.isLoading && !people.isError && people.data?.length === 0 ? <p className="text-meta text-ink-secondary">
      {can("project_members.manage")
        ? "No active project members are available. Finish or cancel this form before adding a person in Team members."
        : "No active project members are available. Ask a Project Manager or PMO Analyst to add a member."}
    </p> : null}
  </div>;
}