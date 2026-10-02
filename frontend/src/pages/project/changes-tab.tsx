import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { ChangeRequestFormDrawer } from "@/components/governance/change-request-form-drawer";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { ErrorState } from "@/components/ui/error-state";
import { Field, Select, TextArea } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/loading-skeleton";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, severityTone, statusTone } from "@/components/ui/status-badge";
import { ApiError, useAuth } from "@/lib/auth";
import { formatDate, formatDays } from "@/lib/format";
import { useChangeImpact, useChangeRequests, useDecideChangeRequest } from "@/lib/queries";
import type { ChangeRequest } from "@/types/api";

interface ChangesTabProps {
  projectId?: string;
  showProjectColumn?: boolean;
}

const DECIDED_STATUSES = new Set(["approved", "rejected"]);

/** A request is open to a decision until an outcome has been recorded against it. */
function awaitingDecision(request: ChangeRequest): boolean {
  return !DECIDED_STATUSES.has(request.status.toLowerCase());
}

export function ChangesTab({ projectId, showProjectColumn = false }: ChangesTabProps): JSX.Element {
  const { can, user } = useAuth();
  const changeRequests = useChangeRequests(projectId);
  const [selected, setSelected] = useState<ChangeRequest | null>(null);
  const impact = useChangeImpact(selected?.change_request_id ?? null);
  const decide = useDecideChangeRequest();
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [confirmDecision,setConfirmDecision] = useState(false);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");

  const canDecide = can("change.decide");
  const canRaise = Boolean(projectId) && can("change.create");
  // The API refuses an outcome from whoever raised the request; administrators keep an exception.
  const raisedByReader = (request: ChangeRequest) =>
    user !== null && user.role !== "administrator" && request.requested_by === user.full_name;

  function open(row: ChangeRequest): void {
    setNotice("");
    setSelected(row);
    setDecision("");
    setRationale("");
    setDecisionError(null);
    setConfirmDecision(false);
  }

  async function recordDecision(): Promise<void> {
    if (!selected) return;
    setDecisionError(null);
    if (selected.row_version == null) {
      setDecisionError("Refresh this change request before recording its decision.");
      return;
    }
    if (!decision) {
      setDecisionError("Choose Approved or Rejected.");
      return;
    }
    if (rationale.trim().length < 10) {
      setDecisionError("Record the reasoning. A decision without a rationale cannot be audited.");
      return;
    }
    if (!confirmDecision) {
      setConfirmDecision(true);
      return;
    }
    try {
      await decide.mutateAsync({
        changeRequestId: selected.change_request_id,
        decision,
        rationale: rationale.trim(),
        rowVersion: selected.row_version,
      });
      setSelected(null);
    } catch (caught) {
      setConfirmDecision(false);
      setDecisionError(caught instanceof ApiError ? caught.message : "The decision could not be recorded.");
    }
  }

  const columns: Column<ChangeRequest>[] = [
    {
      key: "change",
      header: "Change request",
      value: (row) => row.change_description,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-medium text-ink">{row.change_description}</p>
          <p className="text-meta text-ink-secondary">
            {row.change_request_id} · affects {row.requirement_id}
          </p>
        </div>
      ),
    },
    ...(showProjectColumn
      ? [
          {
            key: "project",
            header: "Project",
            value: (row: ChangeRequest) => row.project_id,
            cell: (row: ChangeRequest) => (
              <Link
                to={`/projects/${row.project_id}`}
                className="text-accent hover:underline"
                onClick={(event) => event.stopPropagation()}
              >
                {row.project_id}
              </Link>
            ),
          },
        ]
      : []),
    {
      key: "priority",
      header: "Priority",
      value: (row) => row.priority,
      cell: (row) => <StatusBadge label={row.priority} tone={severityTone(row.priority)} />,
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
    },
    {
      key: "requested_by",
      header: "Requested by",
      value: (row) => row.requested_by ?? "",
      cell: (row) => row.requested_by ?? "Not recorded",
    },
    {
      key: "requested",
      header: "Raised",
      align: "right",
      value: (row) => row.requested_date,
      cell: (row) => formatDate(row.requested_date),
    },
  ];

  return (
    <>
      {notice ? <p role="status" className="mb-3 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
      <DataTable
        rows={changeRequests.data}
        columns={columns}
        rowKey={(row) => row.change_request_id}
        isLoading={changeRequests.isLoading}
        error={changeRequests.isError ? changeRequests.error : undefined}
        onRetry={() => void changeRequests.refetch()}
        onRowClick={open}
        searchPlaceholder="Filter change requests"
        emptyTitle="No change requests"
        emptyDescription="Requests to change a requirement appear here with their calculated downstream impact."
        toolbar={<>
          {canRaise ? <Button size="sm" variant="primary" onClick={() => { setNotice(""); setCreating(true); }}><Plus aria-hidden="true" className="h-4 w-4" />Raise change request</Button> : null}
          <span className="text-meta text-ink-secondary">Select a row to see its impact</span>
        </>}
      />
      {creating && projectId ? <ChangeRequestFormDrawer projectId={projectId} onClose={() => setCreating(false)}
        onSaved={changeRequest => setNotice(`Change request ${changeRequest.change_request_id} raised. Open it to review the calculated impact.`)} /> : null}

      <Drawer
        open={selected !== null}
        dirty={rationale.trim().length>0}
        busy={decide.isPending}
        onClose={() => setSelected(null)}
        title={selected?.change_request_id ?? "Change request"}
        description={selected ? `Raised against ${selected.requirement_id}` : undefined}
        width="max-w-2xl"
        footer={(close) =>
          canDecide && selected && awaitingDecision(selected) && !raisedByReader(selected) ? (
            <>
              <Button onClick={close}>Cancel</Button>
              <Button variant="primary" onClick={() => void recordDecision()} disabled={decide.isPending}>
                {decide.isPending ? "Recording" : confirmDecision ? "Confirm decision" : "Record decision"}
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
              <p className="text-body text-ink">{selected.change_description}</p>
              <p className="mt-2 text-meta text-ink-secondary">
                <span className="font-medium text-ink">Reason: </span>
                {selected.reason}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <StatusBadge label={selected.status} tone={statusTone(selected.status)} />
                <StatusBadge label={selected.priority} tone={severityTone(selected.priority)} />
                <span className="text-meta text-ink-secondary">
                  Raised {formatDate(selected.requested_date)} by {selected.requested_by ?? "an unnamed requester"}
                </span>
              </div>
            </div>

            <section className="card">
              <header className="card-header">
                <h3 className="card-title">Downstream impact</h3>
              </header>
              <div className="card-body">
                {impact.isLoading ? (
                  <div className="space-y-2">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-16 w-full" />
                  </div>
                ) : impact.isError ? (
                  <ErrorState error={impact.error} onRetry={() => void impact.refetch()} />
                ) : impact.data ? (
                  <>
                    <div className="flex flex-wrap items-center gap-4">
                      <div>
                        <p className="text-meta text-ink-secondary">Estimated schedule impact</p>
                        {impact.data.evidence_status === "Insufficient evidence" ? (
                          <p className="text-[24px] font-semibold leading-tight text-ink-secondary">Not assessed</p>
                        ) : (
                          <p className="text-[24px] font-semibold leading-tight text-ink" data-numeric>
                            {formatDays(impact.data.estimated_schedule_impact_days)}
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="text-meta text-ink-secondary">Risk level</p>
                        {impact.data.evidence_status === "Insufficient evidence" ? (
                          <StatusBadge label="Insufficient evidence" tone="warn" className="mt-1" />
                        ) : (
                          <StatusBadge
                            label={impact.data.risk_level}
                            tone={severityTone(impact.data.risk_level)}
                            className="mt-1"
                          />
                        )}
                      </div>
                    </div>

                    {impact.data.evidence_status === "Insufficient evidence" ? (
                      <p className="mt-3 text-body text-ink">
                        Nothing downstream is traced to this requirement yet, so the impact cannot be assessed.
                      </p>
                    ) : null}
                    <p className="mt-3 text-body text-ink-secondary">{impact.data.explanation}</p>

                    <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {[
                        ["Tasks", impact.data.affected_task_ids],
                        ["Test cases", impact.data.affected_test_case_ids],
                        ["Milestones", impact.data.affected_milestone_ids],
                        ["Dependencies", impact.data.affected_dependency_ids],
                      ].map(([label, ids]) => (
                        <div key={label as string} className="rounded-md bg-surface-subtle px-3 py-2">
                          <dt className="text-meta text-ink-secondary">{label as string}</dt>
                          <dd className="text-body font-semibold text-ink" data-numeric>
                            {(ids as string[]).length}
                          </dd>
                        </div>
                      ))}
                    </dl>

                    {impact.data.assumptions_or_limitations.length > 0 ? (
                      <details className="disclosure mt-3">
                        <summary className="text-meta">How this estimate was reached ({impact.data.assumptions_or_limitations.length})</summary>
                        <ul className="list-disc space-y-0.5 px-4 py-3 pl-8 text-meta text-ink-secondary">
                          {impact.data.assumptions_or_limitations.map((line) => (
                            <li key={line}>{line}</li>
                          ))}
                        </ul>
                      </details>
                    ) : null}

                    <SourceList ids={impact.data.source_ids} className="mt-3" label="Calculated from" />
                  </>
                ) : null}
              </div>
            </section>

            {canDecide && awaitingDecision(selected) && raisedByReader(selected) ? (
              <p className="rounded-md border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                You raised this change request, so another person with decision rights records its outcome.
              </p>
            ) : canDecide && awaitingDecision(selected) ? (
              <section className="space-y-3 border-t border-line pt-4">
                <h3 className="text-section font-semibold text-ink">Record a decision</h3>
                <Field label="Decision" htmlFor="decision" required>
                  <Select id="decision" value={decision} onChange={(event) => {setDecision(event.target.value);setConfirmDecision(false);}}>
                    <option value="">Choose a decision</option>
                    <option value="Approved">Approved</option>
                    <option value="Rejected">Rejected</option>
                  </Select>
                </Field>
                <Field
                  label="Rationale"
                  htmlFor="rationale"
                  hint="Stored with your name against the change request."
                  {...(decisionError ? { error: decisionError } : {})}
                >
                  <TextArea
                    id="rationale"
                    rows={4}
                    value={rationale}
                    onChange={(event) => {setRationale(event.target.value);setConfirmDecision(false);}}
                    placeholder="Explain what was considered and why this outcome was chosen."
                  />
                </Field>
                {confirmDecision ? <div role="alert" className="rounded-control border border-warn bg-warn-tint p-3 text-body"><p className="font-medium">Confirm {decision} for {selected.change_request_id}</p><p className="mt-1">This records your decision and rationale. It does not approve any other affected record, and it does not move forecast dates: update the affected milestones and tasks once the change is approved.</p></div> : null}
              </section>
            ) : !awaitingDecision(selected) ? (
              <p className="rounded-md border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                This change request has already been decided. Its outcome is recorded in the audit trail.
              </p>
            ) : (
              <p className="rounded-md border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                Your role can review this impact but cannot record the decision.
              </p>
            )}
          </div>
        ) : null}
      </Drawer>
    </>
  );
}
