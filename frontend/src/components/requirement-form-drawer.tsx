import { useId, useState } from "react";

import { isStaleVersion } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useCreateRequirement, useUpdateRequirement } from "@/lib/queries";
import type { Requirement, RequirementCreateInput } from "@/types/api";

// Types recorded in this workspace. The API accepts other wording, so a stored type is kept as a choice.
const TYPES: readonly string[] = ["Functional", "Performance", "Safety", "Compliance"];
// The priority and status vocabularies the API accepts.
const PRIORITIES: readonly string[] = ["Critical", "High", "Medium", "Low"];
const STATUSES: readonly string[] = ["Draft", "Approved", "Changed", "Superseded", "Retired"];

interface Draft {
  text: string;
  type: string;
  priority: string;
  status: string;
  owner: string | null;
}

/** A recorded value in the spelling EPOS uses, or unchanged when EPOS does not recognise it. */
function canonical(value: string | undefined, options: readonly string[], fallback: string): string {
  if (!value) return fallback;
  return options.find(option => option.toLowerCase() === value.trim().toLowerCase()) ?? value;
}

function choicesWith(value: string, options: readonly string[]): string[] {
  return options.includes(value) ? [...options] : [...options, value];
}

/** Create a requirement, or edit one with its stored version. Only changed fields are sent on edit. */
export function RequirementFormDrawer({ projectId, requirement, onClose, onSaved }: {
  projectId: string;
  requirement?: Requirement;
  onClose: () => void;
  onSaved?: (requirement: Requirement) => void;
}): JSX.Element {
  const formId = useId();
  const createRequirement = useCreateRequirement();
  const updateRequirement = useUpdateRequirement(projectId);
  const mutation = requirement ? updateRequirement : createRequirement;
  const [initial] = useState<Draft>(() => ({
    text: requirement?.requirement_text ?? "",
    type: canonical(requirement?.requirement_type, TYPES, "Functional"),
    priority: canonical(requirement?.priority, PRIORITIES, "Medium"),
    status: canonical(requirement?.status, STATUSES, "Draft"),
    owner: requirement?.owner ?? null,
  }));
  const [draft, setDraft] = useState<Draft>(initial);
  const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};
  const text = draft.text.trim();

  function changes(): Partial<Omit<RequirementCreateInput, "project_id">> {
    const result: Partial<Omit<RequirementCreateInput, "project_id">> = {};
    if (text !== initial.text) result.requirement_text = text;
    if (draft.type !== initial.type) result.requirement_type = draft.type;
    if (draft.priority !== initial.priority) result.priority = draft.priority;
    if (draft.status !== initial.status) result.status = draft.status;
    if (draft.owner !== initial.owner) result.owner = draft.owner;
    return result;
  }

  const changed = Object.keys(changes()).length > 0;
  const dirty = draft.text !== initial.text || changed;
  const canSave = Boolean(text) && !mutation.isPending && (requirement ? changed && requirement.row_version != null : true);

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      let saved: Requirement;
      if (requirement) {
        if (requirement.row_version == null) return;
        saved = await updateRequirement.mutateAsync({
          requirementId: requirement.requirement_id,
          patch: { ...changes(), row_version: requirement.row_version },
        });
      } else {
        saved = await createRequirement.mutateAsync({
          project_id: projectId,
          requirement_text: text,
          requirement_type: draft.type,
          priority: draft.priority,
          status: draft.status,
          ...(draft.owner ? { owner: draft.owner } : {}),
        });
      }
      onSaved?.(saved);
      onClose();
    } catch {
      // Server validation errors stay with the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={mutation.isPending}
    title={requirement ? "Edit requirement" : "New requirement"}
    description={requirement ? requirement.requirement_id : "Link it to the work and tests that realise it once it is saved."}
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{mutation.isPending ? "Saving" : requirement ? "Save changes" : "Create requirement"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Requirement text" htmlFor={`${formId}-text`} error={fieldErrors.requirement_text}
        hint="One verifiable statement, for example what the system shall do.">
        <TextArea id={`${formId}-text`} rows={3} required maxLength={1000} value={draft.text}
          onChange={event => setDraft(current => ({ ...current, text: event.target.value }))} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Type" htmlFor={`${formId}-type`} error={fieldErrors.requirement_type}>
          <Select id={`${formId}-type`} value={draft.type} onChange={event => setDraft(current => ({ ...current, type: event.target.value }))}>
            {choicesWith(initial.type, TYPES).map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Priority" htmlFor={`${formId}-priority`} error={fieldErrors.priority}>
          <Select id={`${formId}-priority`} value={draft.priority} onChange={event => setDraft(current => ({ ...current, priority: event.target.value }))}>
            {choicesWith(initial.priority, PRIORITIES).map(value => <option key={value} value={value} disabled={!PRIORITIES.includes(value)}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Status" htmlFor={`${formId}-status`} error={fieldErrors.status}>
          <Select id={`${formId}-status`} value={draft.status} onChange={event => setDraft(current => ({ ...current, status: event.target.value }))}>
            {choicesWith(initial.status, STATUSES).map(value => <option key={value} value={value} disabled={!STATUSES.includes(value)}>{value}</option>)}
          </Select>
        </Field>
      </div>
      <RecordOwnerField projectId={projectId} purpose="requirement" label="Owner" id={`${formId}-owner`}
        value={draft.owner} error={fieldErrors.owner}
        onChange={owner => setDraft(current => ({ ...current, owner }))} />
      {mutation.isError ? <div role="alert" className="text-body text-critical">
        <p>{mutation.error.message}</p>
        {isStaleVersion(mutation.error) ? <p className="mt-2">Close this panel and reopen the requirement to review the latest version before saving again.</p> : null}
      </div> : null}
    </form>
  </Drawer>;
}
