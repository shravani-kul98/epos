import { useState } from "react";
import { Plus } from "lucide-react";

import { RecordOwnerField } from "@/components/record-owner-field";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, todayIso } from "@/lib/format";
import { useChangeRequests, useCreateDecision, useDecisions, useRecordDecisionOutcome, useUpdateDecision } from "@/lib/queries";
import type { Decision } from "@/types/api";

const CATEGORIES = ["Schedule", "Scope", "Supply", "Technical", "Commercial", "Quality"];
const OUTCOMES = ["Approved", "Rejected", "Superseded"];

function decisionTone(status: string): Tone {
  const value = status.toLowerCase();
  if (value === "approved") return "ok";
  if (value === "rejected") return "critical";
  if (value === "superseded") return "neutral";
  return "warn";
}

/** Record a new decision, or amend one that is still proposed. EPOS allocates the reference. */
function DecisionFormDrawer({ projectId, decision, onClose }: {
  projectId: string;
  decision: Decision | null;
  onClose: () => void;
}): JSX.Element {
  const createDecision = useCreateDecision();
  const updateDecision = useUpdateDecision();
  const changeRequests = useChangeRequests(projectId);
  const mutation = decision ? updateDecision : createDecision;
  const [draft, setDraft] = useState({
    title: decision?.title ?? "",
    description: decision?.description ?? "",
    category: decision?.category ?? "Schedule",
    owner: decision?.owner ?? "",
    changeRequest: decision?.related_change_request_id ?? "",
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [ownerError, setOwnerError] = useState<string | undefined>();
  const dirty = decision
    ? draft.title !== decision.title || draft.description !== decision.description || draft.category !== decision.category
      || draft.owner !== decision.owner || draft.changeRequest !== (decision.related_change_request_id ?? "")
    : Boolean(draft.title || draft.description || draft.owner || draft.changeRequest);

  async function submit(): Promise<void> {
    setCreateError(null);
    setOwnerError(undefined);
    if (draft.title.trim().length < 5 || draft.description.trim().length < 10 || !draft.owner.trim()) {
      if (!draft.owner.trim()) setOwnerError("Choose a registered project member.");
      setCreateError("Give the decision a title of at least 5 characters, a description of at least 10, and an owner.");
      return;
    }
    const values = {
      title: draft.title.trim(),
      description: draft.description.trim(),
      category: draft.category,
      owner: draft.owner.trim(),
      related_change_request_id: draft.changeRequest || null,
    };
    try {
      if (decision) await updateDecision.mutateAsync({ decision, patch: values });
      else await createDecision.mutateAsync({ ...values, project_id: projectId, decision_date: todayIso() });
      onClose();
    } catch (caught) {
      if (caught instanceof ApiError) setOwnerError(caught.fieldErrors.owner);
      setCreateError(caught instanceof ApiError ? caught.message : "The decision could not be saved.");
    }
  }

  return (
    <Drawer
      open
      dirty={dirty}
      busy={mutation.isPending}
      onClose={onClose}
      title={decision ? `Edit ${decision.decision_id}` : "Record a decision"}
      description={decision ? "It stays proposed until someone with authority records an outcome." : "It is proposed until someone with authority records an outcome."}
      footer={(close) =>
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={() => void submit()} disabled={mutation.isPending}>
            {mutation.isPending ? "Saving" : decision ? "Save changes" : "Record decision"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Title" htmlFor="decision-title" required>
          <TextInput
            id="decision-title"
            value={draft.title}
            onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            placeholder="Move the pilot to the following quarter"
          />
        </Field>
        <Field label="Description" htmlFor="decision-description" required>
          <TextArea
            id="decision-description"
            rows={3}
            value={draft.description}
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            placeholder="What is being decided, and what was considered."
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Category" htmlFor="decision-category">
            <Select
              id="decision-category"
              value={draft.category}
              onChange={(event) => setDraft({ ...draft, category: event.target.value })}
            >
              {CATEGORIES.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </Select>
          </Field>
          <RecordOwnerField
            projectId={projectId}
            purpose="decision"
            label="Owner"
            id="decision-owner"
            required
            value={draft.owner || null}
            error={ownerError}
            onChange={(name) => { setDraft({ ...draft, owner: name ?? "" }); setOwnerError(undefined); }}
          />
        </div>
        <Field label="Related change request" htmlFor="decision-change-request"
          hint="Optional. The change request this decision settles.">
          <Select id="decision-change-request" value={draft.changeRequest} disabled={changeRequests.isLoading}
            onChange={(event) => setDraft({ ...draft, changeRequest: event.target.value })}>
            <option value="">{changeRequests.isLoading ? "Loading change requests" : "None"}</option>
            {(changeRequests.data ?? []).map(change => (
              <option key={change.change_request_id} value={change.change_request_id}>
                {change.change_request_id} · {change.change_description}
              </option>
            ))}
          </Select>
        </Field>
        {createError ? (
          <p
            className="rounded-control border border-critical/25 bg-critical-tint px-3 py-2 text-meta text-critical"
            role="alert"
          >
            {createError}
          </p>
        ) : null}
      </div>
    </Drawer>
  );
}

interface DecisionsTabProps {
  projectId?: string;
  showProjectColumn?: boolean;
}

export function DecisionsTab({ projectId, showProjectColumn = false }: DecisionsTabProps): JSX.Element {
  const { can } = useAuth();
  const decisions = useDecisions(projectId);
  const recordOutcome = useRecordDecisionOutcome();

  const [selected, setSelected] = useState<Decision | null>(null);
  const [outcome, setOutcome] = useState("");
  const [rationale, setRationale] = useState("");
  const [outcomeError, setOutcomeError] = useState<string | null>(null);
  const [confirmOutcome, setConfirmOutcome] = useState(false);

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Decision | null>(null);

  const canPropose = can("change.create");
  const canDecide = can("change.decide");
  const awaitingOutcome = (decision: Decision) => decision.status.toLowerCase() === "proposed";

  function open(decision: Decision): void {
    setSelected(decision);
    setOutcome("");
    setRationale("");
    setOutcomeError(null);
    setConfirmOutcome(false);
  }

  async function submitOutcome(): Promise<void> {
    if (!selected) return;
    setOutcomeError(null);
    if (selected.row_version == null) {
      setOutcomeError("Refresh this decision before recording its outcome.");
      return;
    }
    if (!outcome) {
      setOutcomeError("Choose an outcome.");
      return;
    }
    if (rationale.trim().length < 10) {
      setOutcomeError("Record the reasoning. A decision without it cannot be understood later.");
      return;
    }
    if (!confirmOutcome) {
      setConfirmOutcome(true);
      return;
    }
    try {
      await recordOutcome.mutateAsync({
        decisionId: selected.decision_id,
        outcome,
        rationale: rationale.trim(),
        rowVersion: selected.row_version,
      });
      setSelected(null);
    } catch (caught) {
      setConfirmOutcome(false);
      setOutcomeError(caught instanceof ApiError ? caught.message : "The outcome could not be saved.");
    }
  }

  const columns: Column<Decision>[] = [
    {
      key: "decision",
      header: "Decision",
      value: (row) => row.title,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-medium text-ink">{row.title}</p>
          <p className="text-meta text-ink-muted">
            {row.decision_id} · {row.category}
          </p>
        </div>
      ),
    },
    ...(showProjectColumn
      ? [
          {
            key: "project",
            header: "Project",
            value: (row: Decision) => row.project_id,
            cell: (row: Decision) => row.project_id,
          },
        ]
      : []),
    { key: "owner", header: "Owner", value: (row) => row.owner, cell: (row) => row.owner },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={decisionTone(row.status)} />,
    },
    {
      key: "date",
      header: "Decided",
      align: "right",
      value: (row) => row.approval_date ?? "",
      cell: (row) => (awaitingOutcome(row) || !row.approval_date ? "—" : formatDate(row.approval_date)),
    },
  ];

  return (
    <>
      <DataTable
        rows={decisions.data}
        columns={columns}
        rowKey={(row) => row.decision_id}
        isLoading={decisions.isLoading}
        error={decisions.isError ? decisions.error : undefined}
        onRetry={() => void decisions.refetch()}
        onRowClick={open}
        searchPlaceholder="Filter decisions"
        emptyTitle="No decisions recorded"
        emptyDescription="Record decisions as they are made, so the reasoning survives the meeting they were made in."
        emptyAction={
          canPropose && projectId ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              Record a decision
            </Button>
          ) : undefined
        }
        toolbar={
          canPropose && projectId ? (
            <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              Record decision
            </Button>
          ) : undefined
        }
      />

      <Drawer
        open={selected !== null}
        dirty={rationale.trim().length>0}
        busy={recordOutcome.isPending}
        onClose={() => setSelected(null)}
        title={selected?.title ?? "Decision"}
        description={selected ? `${selected.decision_id} · ${selected.category}` : undefined}
        width="max-w-2xl"
        footer={(close) =>
          canDecide && selected && awaitingOutcome(selected) ? (
            <>
              <Button onClick={close}>Cancel</Button>
              <Button variant="primary" onClick={() => void submitOutcome()} disabled={recordOutcome.isPending}>
                {recordOutcome.isPending ? "Recording" : confirmOutcome ? "Confirm outcome" : "Record outcome"}
              </Button>
            </>
          ) : (
            <Button onClick={close}>Close</Button>
          )
        }
      >
        {selected ? (
          <div className="space-y-5">
            <div>
              <p className="text-body text-ink">{selected.description}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusBadge label={selected.status} tone={decisionTone(selected.status)} />
                <span className="text-meta text-ink-muted">
                  Owned by {selected.owner} · proposed {formatDate(selected.decision_date)}
                  {selected.approval_date && !awaitingOutcome(selected) ? ` · decided ${formatDate(selected.approval_date)}` : ""}
                </span>
                {canPropose && projectId && awaitingOutcome(selected) ? (
                  <Button size="sm" className="ml-auto" onClick={() => { setEditing(selected); setSelected(null); }}>Edit decision</Button>
                ) : null}
              </div>
            </div>

            {selected.rationale ? (
              <section className="rounded-card border border-line bg-surface-subtle px-3 py-2.5">
                <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                  Reasoning
                </h3>
                <p className="mt-1 text-body text-ink">{selected.rationale}</p>
                {selected.approver ? (
                  <p className="mt-1.5 text-meta text-ink-muted">
                    Recorded by {selected.approver} on {formatDate(selected.approval_date)}
                  </p>
                ) : null}
              </section>
            ) : null}

            {selected.delivery_impact ? (
              <div>
                <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                  Delivery impact
                </h3>
                <p className="mt-1 text-body text-ink">{selected.delivery_impact}</p>
              </div>
            ) : null}

            {[
              ["Milestone", selected.related_milestone_id],
              ["Risk", selected.related_risk_id],
              ["Change request", selected.related_change_request_id],
              ["Requirement", selected.related_requirement_id],
            ].some(([, value]) => value) ? (
              <div>
                <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">
                  Related records
                </h3>
                <ul className="mt-1.5 flex flex-wrap gap-1.5">
                  {(
                    [
                      ["Milestone", selected.related_milestone_id],
                      ["Risk", selected.related_risk_id],
                      ["Change request", selected.related_change_request_id],
                      ["Requirement", selected.related_requirement_id],
                    ] as [string, string | null][]
                  )
                    .filter(([, value]) => value)
                    .map(([label, value]) => (
                      <li
                        key={label}
                        className="rounded border border-line bg-surface-subtle px-2 py-1 text-meta text-ink-secondary"
                      >
                        {label} {value}
                      </li>
                    ))}
                </ul>
              </div>
            ) : null}

            {canDecide && awaitingOutcome(selected) ? (
              <section className="space-y-3 border-t border-line pt-4">
                <h3 className="text-section font-semibold text-ink">Record an outcome</h3>
                <Field label="Outcome" htmlFor="decision-outcome" required>
                  <Select
                    id="decision-outcome"
                    value={outcome}
                    onChange={(event) => {setOutcome(event.target.value);setConfirmOutcome(false);}}
                  >
                    <option value="">Choose an outcome</option>
                    {OUTCOMES.map(value => <option key={value} value={value}>{value}</option>)}
                  </Select>
                </Field>
                <Field
                  label="Reasoning"
                  htmlFor="decision-rationale"
                  hint="Stored against the decision with your name."
                  {...(outcomeError ? { error: outcomeError } : {})}
                >
                  <TextArea
                    id="decision-rationale"
                    rows={4}
                    value={rationale}
                    onChange={(event) => {setRationale(event.target.value);setConfirmOutcome(false);}}
                    placeholder="Explain what was considered and why this outcome was chosen."
                  />
                </Field>
                {confirmOutcome ? <div role="alert" className="rounded-control border border-warn bg-warn-tint p-3 text-body"><p className="font-medium">Confirm {outcome} for {selected.decision_id}</p><p className="mt-1">Your reasoning and identity will be recorded in the audit trail. Confirm only after reviewing the evidence.</p></div> : null}
              </section>
            ) : !awaitingOutcome(selected) ? (
              <p className="rounded-control border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                This decision already has a recorded outcome.
              </p>
            ) : (
              <p className="rounded-control border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                Your role can review this decision but cannot record its outcome.
              </p>
            )}
          </div>
        ) : null}
      </Drawer>

      {projectId && (creating || editing) ? (
        <DecisionFormDrawer
          key={editing?.decision_id ?? "new"}
          projectId={projectId}
          decision={editing}
          onClose={() => { setCreating(false); setEditing(null); }}
        />
      ) : null}
    </>
  );
}
