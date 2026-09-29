import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { todayIso } from "@/lib/format";
import { useCreateChangeRequest, useRequirements } from "@/lib/queries";
import type { ChangeRequest } from "@/types/api";

const PRIORITIES: readonly string[] = ["Critical", "High", "Medium", "Low"];

/** Raise a change against a recorded requirement. Its downstream impact is calculated by EPOS. */
export function ChangeRequestFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (changeRequest: ChangeRequest) => void;
}): JSX.Element {
  const formId = useId();
  const requirements = useRequirements(projectId);
  const create = useCreateChangeRequest();
  const [requirementId, setRequirementId] = useState("");
  const [description, setDescription] = useState("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [requested, setRequested] = useState(todayIso);
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const noRequirements = !requirements.isLoading && !requirements.isError && (requirements.data?.length ?? 0) === 0;
  const dirty = Boolean(requirementId || description || reason);
  const canSave = Boolean(requirementId && description.trim() && reason.trim() && requested) && !create.isPending;

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      const changeRequest = await create.mutateAsync({
        project_id: projectId,
        requirement_id: requirementId,
        change_description: description.trim(),
        reason: reason.trim(),
        priority,
        requested_date: requested,
      });
      onSaved?.(changeRequest);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="Raise change request"
    description="Propose a change to a requirement. EPOS calculates what it touches downstream; a decider records the outcome."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave || noRequirements}>{create.isPending ? "Saving" : "Raise change request"}</Button></>}>
    {noRequirements ? <p className="text-body text-ink-secondary">This project has no requirements yet. A change request changes a recorded requirement, so add the requirement first.</p> : (
      <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
        <Field label="Requirement" htmlFor={`${formId}-requirement`} error={fieldErrors.requirement_id}
          hint="The requirement this change would alter.">
          <Select id={`${formId}-requirement`} required value={requirementId} disabled={requirements.isLoading} onChange={event => setRequirementId(event.target.value)}>
            <option value="">{requirements.isLoading ? "Loading requirements" : "Choose a requirement"}</option>
            {(requirements.data ?? []).map(requirement => <option key={requirement.requirement_id} value={requirement.requirement_id}>
              {requirement.requirement_id} · {requirement.requirement_text.length > 80 ? `${requirement.requirement_text.slice(0, 79)}…` : requirement.requirement_text}
            </option>)}
          </Select>
        </Field>
        {requirements.isError ? <div role="alert" className="text-meta text-critical"><p>{requirements.error.message}</p><Button size="sm" onClick={() => void requirements.refetch()}>Retry requirements</Button></div> : null}
        <Field label="Proposed change" htmlFor={`${formId}-description`} error={fieldErrors.change_description}>
          <TextArea id={`${formId}-description`} rows={3} required maxLength={1000} value={description} onChange={event => setDescription(event.target.value)} />
        </Field>
        <Field label="Reason" htmlFor={`${formId}-reason`} error={fieldErrors.reason} hint="Why the change is needed and who asked for it.">
          <TextArea id={`${formId}-reason`} rows={2} required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Priority" htmlFor={`${formId}-priority`} error={fieldErrors.priority}>
            <Select id={`${formId}-priority`} value={priority} onChange={event => setPriority(event.target.value)}>
              {PRIORITIES.map(value => <option key={value} value={value}>{value}</option>)}
            </Select>
          </Field>
          <Field label="Requested on" htmlFor={`${formId}-requested`} error={fieldErrors.requested_date}>
            <TextInput id={`${formId}-requested`} type="date" required value={requested} onChange={event => setRequested(event.target.value)} />
          </Field>
        </div>
        <p className="text-meta text-ink-secondary">You are recorded as the requester. The request does not edit the requirement itself; update the requirement once the change is approved.</p>
        <MutationError error={create.error} />
      </form>
    )}
  </Drawer>;
}
