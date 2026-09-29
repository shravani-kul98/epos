import { useId, useState } from "react";

import { MutationError } from "@/components/governance/lifecycle-section";
import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { ApiError } from "@/lib/api";
import { todayIso } from "@/lib/format";
import { useCreateIssue, useRisks, useUpdateIssue } from "@/lib/queries";
import type { Issue, Severity } from "@/types/api";

const SEVERITIES: readonly Severity[] = ["Critical", "High", "Medium", "Low"];
const RISK_SOURCE = /^Risk (\S+)$/;

/** Raise an issue, or amend one. EPOS allocates its reference. */
export function IssueFormDrawer({ projectId, issue, onClose, onSaved }: {
  projectId: string;
  /** The issue to amend. Without it a new issue is raised. */
  issue?: Issue;
  onClose: () => void;
  onSaved?: (issue: Issue) => void;
}): JSX.Element {
  const formId = useId();
  const create = useCreateIssue();
  const update = useUpdateIssue();
  const risks = useRisks(projectId);
  const mutation = issue ? update : create;
  const initialRisk = issue?.source_reference?.match(RISK_SOURCE)?.[1] ?? "";
  const [title, setTitle] = useState(issue?.title ?? "");
  const [description, setDescription] = useState(issue?.description ?? "");
  const [severity, setSeverity] = useState<Severity>(issue?.severity ?? "High");
  const [owner, setOwner] = useState<string | null>(issue?.owner ?? null);
  const [ownerId, setOwnerId] = useState<number | null>(issue?.owner_user_id ?? null);
  const [raised, setRaised] = useState(issue?.raised_date ?? todayIso());
  const [target, setTarget] = useState(issue?.target_resolution_date ?? "");
  const [fromRisk, setFromRisk] = useState(initialRisk);
  const [source, setSource] = useState(initialRisk ? "" : issue?.source_reference ?? "");
  const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {};
  const dirty = issue
    ? title !== issue.title || description !== issue.description || severity !== issue.severity
      || owner !== issue.owner || target !== (issue.target_resolution_date ?? "") || fromRisk !== initialRisk
    : Boolean(title || description || owner || target || source || fromRisk);
  const canSave = Boolean(title.trim() && description.trim() && raised) && !mutation.isPending;
  const sourceReference = fromRisk ? `Risk ${fromRisk}` : source.trim() || null;

  async function save(): Promise<void> {
    if (!canSave) return;
    const values = {
      title: title.trim(),
      description: description.trim(),
      severity,
      owner,
      owner_user_id: ownerId,
      target_resolution_date: target || null,
      source_reference: sourceReference,
    };
    try {
      const saved = issue
        ? await update.mutateAsync({ issue, patch: values })
        : await create.mutateAsync({ ...values, project_id: projectId, raised_date: raised });
      onSaved?.(saved);
      onClose();
    } catch {
      // Server validation stays beside the entered values.
    }
  }

  return <Drawer open onClose={onClose} dirty={dirty} busy={mutation.isPending} title={issue ? `Edit ${issue.issue_id}` : "Raise issue"}
    description={issue ? "Changes are recorded in the audit trail with your name." : "A problem that has already happened. A risk that materialises belongs here."}
    footer={close => <><Button onClick={close}>Cancel</Button><Button type="submit" form={formId} variant="primary" disabled={!canSave}>{mutation.isPending ? "Saving" : issue ? "Save changes" : "Raise issue"}</Button></>}>
    <form id={formId} className="space-y-4" onSubmit={event => { event.preventDefault(); void save(); }}>
      <Field label="Title" htmlFor={`${formId}-title`} required error={fieldErrors.title}>
        <TextInput id={`${formId}-title`} required maxLength={200} value={title} onChange={event => setTitle(event.target.value)}
          placeholder="Qualification rig unavailable for two weeks" />
      </Field>
      <Field label="What happened" htmlFor={`${formId}-description`} required error={fieldErrors.description}
        hint="The effect on delivery and who or what is affected.">
        <TextArea id={`${formId}-description`} rows={4} required maxLength={2000} value={description} onChange={event => setDescription(event.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Severity" htmlFor={`${formId}-severity`} error={fieldErrors.severity}>
          <Select id={`${formId}-severity`} value={severity} onChange={event => setSeverity(event.target.value as Severity)}>
            {SEVERITIES.map(value => <option key={value} value={value}>{value}</option>)}
          </Select>
        </Field>
        <Field label="Raised on" htmlFor={`${formId}-raised`} required error={fieldErrors.raised_date}>
          <TextInput id={`${formId}-raised`} type="date" required disabled={Boolean(issue)} value={raised} onChange={event => setRaised(event.target.value)} />
        </Field>
        <Field label="Target resolution" htmlFor={`${formId}-target`} error={fieldErrors.target_resolution_date}>
          <TextInput id={`${formId}-target`} type="date" min={raised || undefined} value={target} onChange={event => setTarget(event.target.value)} />
        </Field>
      </div>
      <RecordOwnerField projectId={projectId} purpose="issue" label="Owner" id={`${formId}-owner`} value={owner}
        userId={ownerId} linksAccount error={fieldErrors.owner ?? fieldErrors.owner_user_id}
        onChange={(name, userId) => { setOwner(name); setOwnerId(userId); }} />
      <Field label="Came from risk" htmlFor={`${formId}-risk`}
        hint="Optional. Link the risk this issue materialised from.">
        <Select id={`${formId}-risk`} value={fromRisk} onChange={event => setFromRisk(event.target.value)} disabled={risks.isLoading}>
          <option value="">{risks.isLoading ? "Loading risks" : "Not from a recorded risk"}</option>
          {(risks.data ?? []).map(risk => <option key={risk.risk_id} value={risk.risk_id}>{risk.risk_id} · {risk.risk_name}</option>)}
        </Select>
      </Field>
      {fromRisk ? null : <Field label="Source reference" htmlFor={`${formId}-source`} error={fieldErrors.source_reference}
        hint="Optional. Where it was recorded, for example a meeting note or test log.">
        <TextInput id={`${formId}-source`} maxLength={500} value={source} onChange={event => setSource(event.target.value)} />
      </Field>}
      <MutationError error={mutation.error} />
    </form>
  </Drawer>;
}
