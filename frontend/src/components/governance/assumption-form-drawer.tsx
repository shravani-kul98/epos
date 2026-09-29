import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useCreateAssumption, useUpdateAssumption } from "@/lib/queries";
import type { Assumption } from "@/types/api";

/** Record an assumption the plan relies on, or amend one. A new one starts Proposed. */
export function AssumptionFormDrawer({ projectId, assumption, onClose, onSaved }: {
  projectId: string;
  /** The assumption to amend. Without it a new assumption is recorded. */
  assumption?: Assumption;
  onClose: () => void;
  onSaved?: (assumption: Assumption) => void;
}): JSX.Element {
  const formId = useId();
  const create = useCreateAssumption();
  const update = useUpdateAssumption();
  const mutation = assumption ? update : create;
  const [text, setText] = useState(assumption?.assumption_text ?? "");
  const [owner, setOwner] = useState<string | null>(assumption?.owner ?? null);
  const [ownerId, setOwnerId] = useState<number | null>(assumption?.owner_user_id ?? null);
  const [due, setDue] = useState(assumption?.validation_due_date ?? "");
  const [impact, setImpact] = useState(assumption?.impact_if_false ?? "");
  const [source, setSource] = useState(assumption?.source_reference ?? "");
  const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};
  const dirty = assumption
    ? text !== assumption.assumption_text || owner !== assumption.owner || due !== (assumption.validation_due_date ?? "")
      || impact !== (assumption.impact_if_false ?? "") || source !== (assumption.source_reference ?? "")
    : Boolean(text || owner || due || impact || source);
  const canSave = Boolean(text.trim() && owner) && !mutation.isPending;

  async function save(): Promise<void> {
    if (!canSave || !owner) return;
    const values = {
      assumption_text: text.trim(),
      owner,
      owner_user_id: ownerId,
      validation_due_date: due || null,
      impact_if_false: impact.trim() || null,
      source_reference: source.trim() || null,
    };
    try {
      const saved = assumption
        ? await update.mutateAsync({ assumption, patch: values })
        : await create.mutateAsync({ ...values, project_id: projectId });
      onSaved?.(saved);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={mutation.isPending} title={assumption ? `Edit ${assumption.assumption_id}` : "Record assumption"}
    description={assumption ? "Changes are recorded in the audit trail with your name." : "Something the plan relies on that is not yet confirmed. It starts as Proposed."}
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{mutation.isPending ? "Saving" : assumption ? "Save changes" : "Record assumption"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Assumption" htmlFor={`${formId}-text`} error={fieldErrors.assumption_text}
        hint="State it so it can be shown true or false, for example what will be available and by when.">
        <TextArea id={`${formId}-text`} rows={3} required maxLength={2000} value={text} onChange={event => setText(event.target.value)} />
      </Field>
      <RecordOwnerField projectId={projectId} purpose="assumption" label="Owner" id={`${formId}-owner`} value={owner} required
        userId={ownerId} linksAccount error={fieldErrors.owner ?? fieldErrors.owner_user_id}
        onChange={(name, userId) => { setOwner(name); setOwnerId(userId); }} />
      <Field label="Validate by" htmlFor={`${formId}-due`} error={fieldErrors.validation_due_date}
        hint="Optional. When the evidence to confirm or disprove it should be in hand.">
        <TextInput id={`${formId}-due`} type="date" value={due} onChange={event => setDue(event.target.value)} />
      </Field>
      <Field label="Impact if false" htmlFor={`${formId}-impact`} error={fieldErrors.impact_if_false}
        hint="Optional. What happens to delivery if it turns out not to hold.">
        <TextArea id={`${formId}-impact`} rows={2} maxLength={1000} value={impact} onChange={event => setImpact(event.target.value)} />
      </Field>
      <Field label="Source reference" htmlFor={`${formId}-source`} error={fieldErrors.source_reference}
        hint="Optional. Where it was agreed, for example a plan review or decision.">
        <TextInput id={`${formId}-source`} maxLength={500} value={source} onChange={event => setSource(event.target.value)} />
      </Field>
      <MutationError error={mutation.error} />
    </form>
  </Drawer>;
}
