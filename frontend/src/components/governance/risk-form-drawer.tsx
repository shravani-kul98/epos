import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useCreateRisk } from "@/lib/queries";
import type { Risk } from "@/types/api";

const LEVELS = [1, 2, 3, 4, 5];
const MITIGATION_STATUSES: readonly string[] = ["Not Started", "In Progress", "Complete", "Not Required"];

/** Record a new risk. Its severity is calculated by EPOS from probability and impact. */
export function RiskFormDrawer({ projectId, onClose, onSaved }: {
  projectId: string;
  onClose: () => void;
  onSaved?: (risk: Risk) => void;
}): JSX.Element {
  const formId = useId();
  const create = useCreateRisk();
  const [name, setName] = useState("");
  const [probability, setProbability] = useState(3);
  const [impact, setImpact] = useState(3);
  const [owner, setOwner] = useState<string | null>(null);
  const [ownerId, setOwnerId] = useState<number | null>(null);
  const [mitigation, setMitigation] = useState("Not Started");
  const [due, setDue] = useState("");
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const dirty = Boolean(name || owner || due);
  const canSave = Boolean(name.trim() && due) && !create.isPending;

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      const risk = await create.mutateAsync({
        project_id: projectId,
        risk_name: name.trim(),
        probability,
        impact,
        status: "Open",
        mitigation_owner: owner,
        mitigation_owner_user_id: ownerId,
        mitigation_status: mitigation,
        due_date: due,
      });
      onSaved?.(risk);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={create.isPending} title="New risk"
    description="Something that could go wrong. It starts Open; EPOS calculates its severity."
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{create.isPending ? "Saving" : "Create risk"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Risk" htmlFor={`${formId}-name`} error={fieldErrors.risk_name} hint="Cause and effect, for example Supplier delay could push qualification past the gate.">
        <TextInput id={`${formId}-name`} required maxLength={200} value={name} onChange={event => setName(event.target.value)} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Probability" htmlFor={`${formId}-probability`} hint="1 is unlikely, 5 is near certain." error={fieldErrors.probability}>
          <Select id={`${formId}-probability`} value={String(probability)} onChange={event => setProbability(Number(event.target.value))}>
            {LEVELS.map(level => <option key={level} value={level}>{level}</option>)}
          </Select>
        </Field>
        <Field label="Impact" htmlFor={`${formId}-impact`} hint="1 is minor, 5 is severe." error={fieldErrors.impact}>
          <Select id={`${formId}-impact`} value={String(impact)} onChange={event => setImpact(Number(event.target.value))}>
            {LEVELS.map(level => <option key={level} value={level}>{level}</option>)}
          </Select>
        </Field>
      </div>
      <RecordOwnerField projectId={projectId} purpose="risk" label="Mitigation owner" id={`${formId}-owner`} value={owner}
        userId={ownerId} linksAccount error={fieldErrors.mitigation_owner ?? fieldErrors.mitigation_owner_user_id}
        onChange={(name, userId) => { setOwner(name); setOwnerId(userId); }} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Mitigation status" htmlFor={`${formId}-mitigation`} error={fieldErrors.mitigation_status}>
          <Select id={`${formId}-mitigation`} value={mitigation} onChange={event => setMitigation(event.target.value)}>
            {MITIGATION_STATUSES.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Due date" htmlFor={`${formId}-due`} error={fieldErrors.due_date} hint="When the mitigation should be in place.">
          <TextInput id={`${formId}-due`} type="date" required value={due} onChange={event => setDue(event.target.value)} />
        </Field>
      </div>
      <MutationError error={create.error} />
    </form>
  </Drawer>;
}
