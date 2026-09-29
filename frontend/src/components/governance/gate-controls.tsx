import { useId, useState } from "react";
import { Plus } from "lucide-react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { CheckboxField, Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { useAssessGateCriterion, useCreateGateCriterion, useRecordGateReview } from "@/lib/queries";
import type { Gate, GateCriterion, GateReviewOutcome } from "@/types/api";

const OUTCOMES: readonly GateReviewOutcome[] = ["Approved", "Approved with Conditions", "Rejected", "Deferred"];

/** Configure one entry or exit criterion while the gate is still being prepared. */
export function GateCriterionForm({ gate }: { gate: Gate }): JSX.Element {
  const id = useId();
  const create = useCreateGateCriterion(gate);
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<"Entry" | "Exit">("Exit");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mandatory, setMandatory] = useState(true);
  const [evidence, setEvidence] = useState(true);
  const fieldErrors = create.error instanceof ApiError ? create.error.fieldErrors : {};
  const canSave = Boolean(name.trim() && description.trim()) && !create.isPending;

  function reset(): void {
    setName("");
    setDescription("");
    setMandatory(true);
    setEvidence(true);
    create.reset();
  }

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      await create.mutateAsync({ criterion_type: type, criterion_name: name.trim(), description: description.trim(), is_mandatory: mandatory, evidence_required: evidence });
      reset();
      setOpen(false);
    } catch {
      // The refusal is shown in the form.
    }
  }

  if (!open) {
    return <Button size="sm" onClick={() => { reset(); setOpen(true); }}><Plus aria-hidden="true" className="h-4 w-4" />Add criterion</Button>;
  }

  return <form aria-label="New gate criterion" className="space-y-3 rounded-control border border-line p-3" onSubmit={event => { event.preventDefault(); void save(); }}>
    <div className="grid gap-3 sm:grid-cols-3">
      <Field label="Type" htmlFor={`${id}-type`} error={fieldErrors.criterion_type}>
        <Select id={`${id}-type`} value={type} onChange={event => setType(event.target.value as "Entry" | "Exit")}>
          <option value="Entry">Entry</option>
          <option value="Exit">Exit</option>
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Field label="Criterion" htmlFor={`${id}-name`} error={fieldErrors.criterion_name}>
          <TextInput id={`${id}-name`} required maxLength={200} value={name} onChange={event => setName(event.target.value)} />
        </Field>
      </div>
    </div>
    <Field label="What must be true" htmlFor={`${id}-description`} error={fieldErrors.description}>
      <TextArea id={`${id}-description`} rows={2} required maxLength={2000} value={description} onChange={event => setDescription(event.target.value)} />
    </Field>
    <div className="grid gap-3 sm:grid-cols-2">
      <CheckboxField id={`${id}-mandatory`} label="Mandatory" hint="An unmet mandatory criterion blocks review." checked={mandatory} onChange={setMandatory} />
      <CheckboxField id={`${id}-evidence`} label="Evidence required" hint="It can be marked met only with an evidence reference." checked={evidence} onChange={setEvidence} />
    </div>
    <MutationError error={create.error} />
    <div className="flex flex-wrap justify-end gap-2">
      <Button size="sm" disabled={create.isPending} onClick={() => setOpen(false)}>Cancel</Button>
      <Button size="sm" type="submit" variant="primary" disabled={!canSave}>{create.isPending ? "Saving" : "Add criterion"}</Button>
    </div>
  </form>;
}

/** Record whether one criterion is met, with the reasoning and any evidence it requires. */
export function GateCriterionAssessment({ gate, criterion }: { gate: Gate; criterion: GateCriterion }): JSX.Element {
  const id = useId();
  const assess = useAssessGateCriterion(gate);
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<"Met" | "Not Met">("Met");
  const [rationale, setRationale] = useState("");
  const [evidence, setEvidence] = useState(criterion.evidence_reference ?? "");
  const needsEvidence = target === "Met" && criterion.evidence_required;
  const canSave = Boolean(rationale.trim()) && (!needsEvidence || Boolean(evidence.trim())) && !assess.isPending && criterion.row_version != null;

  async function save(): Promise<void> {
    if (!canSave) return;
    try {
      await assess.mutateAsync({ criterion, target, rationale: rationale.trim(), evidence: evidence.trim() || undefined });
      setOpen(false);
      setRationale("");
    } catch {
      // The refusal is shown in the form.
    }
  }

  if (!open) {
    return <Button size="sm" aria-label={`Assess ${criterion.criterion_id}`} onClick={() => { assess.reset(); setOpen(true); }}>Assess</Button>;
  }

  return <form aria-label={`Assess ${criterion.criterion_id}`} className="mt-2 w-full space-y-3 rounded-control border border-line bg-surface-subtle p-3"
    onSubmit={event => { event.preventDefault(); void save(); }}>
    <Field label="Assessment" htmlFor={`${id}-target`}>
      <Select id={`${id}-target`} value={target} onChange={event => setTarget(event.target.value as "Met" | "Not Met")}>
        <option value="Met">Met</option>
        <option value="Not Met">Not met</option>
      </Select>
    </Field>
    <Field label="Reasoning" htmlFor={`${id}-rationale`} hint="Kept with the assessment and your name.">
      <TextArea id={`${id}-rationale`} rows={2} required maxLength={2000} value={rationale} onChange={event => setRationale(event.target.value)} />
    </Field>
    <Field label="Evidence reference" htmlFor={`${id}-evidence`}
      hint={needsEvidence ? "Required: this criterion is met only with named evidence, such as a report or review record." : "Optional."}>
      <TextInput id={`${id}-evidence`} maxLength={2000} required={needsEvidence} value={evidence} onChange={event => setEvidence(event.target.value)} />
    </Field>
    <MutationError error={assess.error} />
    <div className="flex flex-wrap justify-end gap-2">
      <Button size="sm" disabled={assess.isPending} onClick={() => setOpen(false)}>Cancel</Button>
      <Button size="sm" type="submit" variant="primary" disabled={!canSave}>{assess.isPending ? "Saving" : "Save assessment"}</Button>
    </div>
  </form>;
}

/** The one immutable human review for the gate's current cycle. */
export function GateReviewForm({ gate }: { gate: Gate }): JSX.Element {
  const id = useId();
  const record = useRecordGateReview(gate);
  const [outcome, setOutcome] = useState<GateReviewOutcome | "">("");
  const [rationale, setRationale] = useState("");
  const [conditions, setConditions] = useState("");
  const [confirming, setConfirming] = useState(false);
  const conditional = outcome === "Approved with Conditions";
  const canSave = Boolean(outcome) && Boolean(rationale.trim()) && (!conditional || Boolean(conditions.trim())) && !record.isPending;

  async function save(): Promise<void> {
    if (!canSave || !outcome) return;
    if (!confirming) {
      setConfirming(true);
      return;
    }
    try {
      await record.mutateAsync({ outcome, rationale: rationale.trim(), conditions: conditional ? conditions.trim() : null });
    } catch {
      setConfirming(false);
    }
  }

  return <form aria-label="Record gate review" className="space-y-3 rounded-card border border-line p-4" onSubmit={event => { event.preventDefault(); void save(); }}>
    <div>
      <h3 className="text-card font-medium text-ink">Record the review decision</h3>
      <p className="mt-0.5 text-meta text-ink-secondary">Review cycle {gate.review_cycle}. A recorded review cannot be edited; a later cycle records a new one.</p>
    </div>
    <Field label="Outcome" htmlFor={`${id}-outcome`} required>
      <Select id={`${id}-outcome`} value={outcome} onChange={event => { setOutcome(event.target.value as GateReviewOutcome | ""); setConfirming(false); }}>
        <option value="">Choose an outcome</option>
        {OUTCOMES.map(value => <option key={value} value={value}>{value}</option>)}
      </Select>
    </Field>
    <Field label="Rationale" htmlFor={`${id}-rationale`} hint="What the reviewers considered and why this outcome was chosen.">
      <TextArea id={`${id}-rationale`} rows={3} required maxLength={2000} value={rationale} onChange={event => { setRationale(event.target.value); setConfirming(false); }} />
    </Field>
    {conditional ? <Field label="Conditions" htmlFor={`${id}-conditions`} hint="Required for a conditional approval. Each condition should be checkable later.">
      <TextArea id={`${id}-conditions`} rows={2} required maxLength={2000} value={conditions} onChange={event => { setConditions(event.target.value); setConfirming(false); }} />
    </Field> : null}
    {confirming ? <div role="alert" className="rounded-control border border-warn bg-warn-tint p-3 text-body">
      <p className="font-medium">Confirm {outcome} for {gate.gate_id}</p>
      <p className="mt-1">This records an immutable review with your name. Closing the gate is a separate step.</p>
    </div> : null}
    <MutationError error={record.error} />
    <div className="flex justify-end">
      <Button size="sm" type="submit" variant="primary" disabled={!canSave}>{record.isPending ? "Recording" : confirming ? "Confirm review" : "Record review"}</Button>
    </div>
  </form>;
}
