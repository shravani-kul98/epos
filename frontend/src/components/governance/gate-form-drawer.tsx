import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useCreateGate, useMilestones } from "@/lib/queries";
import type { Gate } from "@/types/api";

/** Configure a review point. EPOS allocates its reference and the next free sequence. */
export function GateFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (gate: Gate) => void;
}): JSX.Element {
  const formId = useId();
  const milestones = useMilestones(projectId);
  const create = useCreateGate();
  const [name, setName] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [planned, setPlanned] = useState("");
  const [owner, setOwner] = useState<string | null>(null);
  const [baseline, setBaseline] = useState("");
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const dirty = Boolean(name || milestoneId || planned || baseline || owner);
  const canSave = Boolean(name.trim() && planned && owner) && !create.isPending;

  async function save(): Promise<void> {
    if (!canSave || !owner) return;
    try {
      const gate = await create.mutateAsync({
        project_id: projectId,
        milestone_id: milestoneId || null,
        gate_name: name.trim(),
        planned_review_date: planned,
        owner,
        applicable_baseline: baseline.trim() || null,
      });
      onSaved?.(gate);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="New gate"
    description="A review point the project must pass. Add its entry and exit criteria once it exists."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{create.isPending ? "Saving" : "Create gate"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Gate name" htmlFor={`${formId}-name`} error={fieldErrors.gate_name} hint="For example Design review or Release readiness.">
        <TextInput id={`${formId}-name`} required maxLength={200} value={name} onChange={event => setName(event.target.value)} />
      </Field>
      <Field label="Milestone" htmlFor={`${formId}-milestone`} error={fieldErrors.milestone_id}
        hint="Optional. The delivery checkpoint this gate reviews.">
        <Select id={`${formId}-milestone`} value={milestoneId} disabled={milestones.isLoading} onChange={event => setMilestoneId(event.target.value)}>
          <option value="">{milestones.isLoading ? "Loading milestones" : "Not linked to a milestone"}</option>
          {(milestones.data ?? []).map(milestone => <option key={milestone.milestone_id} value={milestone.milestone_id}>{milestone.milestone_name} · {milestone.milestone_id}</option>)}
        </Select>
      </Field>
      <Field label="Planned review date" htmlFor={`${formId}-planned`} error={fieldErrors.planned_review_date}>
        <TextInput id={`${formId}-planned`} type="date" required value={planned} onChange={event => setPlanned(event.target.value)} />
      </Field>
      <RecordOwnerField projectId={projectId} purpose="gate" label="Gate owner" id={`${formId}-owner`} value={owner} required
        error={fieldErrors.owner} onChange={name => setOwner(name)} />
      <Field label="Applicable baseline" htmlFor={`${formId}-baseline`} error={fieldErrors.applicable_baseline}
        hint="Optional. The plan or specification version the gate is reviewed against.">
        <TextInput id={`${formId}-baseline`} maxLength={200} value={baseline} onChange={event => setBaseline(event.target.value)} />
      </Field>
      <MutationError error={create.error} />
    </form>
  </Drawer>;
}
