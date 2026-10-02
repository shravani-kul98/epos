import { useState } from "react";
import { AlertTriangle, CheckCircle2, Plus, ShieldAlert } from "lucide-react";

import { GateCriterionAssessment, GateCriterionForm, GateReviewForm } from "@/components/governance/gate-controls";
import { GateFormDrawer } from "@/components/governance/gate-form-drawer";
import { LifecycleSection, type LifecycleMove } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, Skeleton } from "@/components/ui/loading-skeleton";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime } from "@/lib/format";
import { useGateCriteria, useGateReadiness, useGateReviews, useGates, useTransitionGate } from "@/lib/queries";
import type { Gate, GateReadinessFinding, GateReviewOutcome, GateStatus } from "@/types/api";

// Mirrors the gate lifecycle the API enforces, so only accepted steps are offered.
const GATE_MOVES: readonly LifecycleMove[] = [
  { target: "Preparing", label: "Start preparing", from: ["Not Started"], reasonHint: "For example who is gathering the evidence and by when." },
  { target: "Ready for Review", label: "Mark ready for review", from: ["Preparing"], reasonHint: "EPOS refuses while a mandatory criterion is unmet." },
  { target: "In Review", label: "Begin review", from: ["Ready for Review"] },
  { target: "Preparing", label: "Return to preparing", from: ["Ready for Review"] },
  { target: "Preparing", label: "Prepare the next review cycle", from: ["Failed", "Deferred"] },
  {
    target: "Withdrawn", label: "Withdraw", from: ["Not Started", "Preparing", "Ready for Review", "In Review", "Failed", "Deferred"],
    reasonHint: "Why this review point is no longer needed.", danger: true,
  },
];

// The gate result a recorded review supports. The API checks it against readiness again.
const RESULT_FOR_OUTCOME: Record<GateReviewOutcome, GateStatus> = {
  Approved: "Passed",
  "Approved with Conditions": "Passed with Conditions",
  Rejected: "Failed",
  Deferred: "Deferred",
};

const CONFIGURABLE: readonly string[] = ["Not Started", "Preparing"];

function gateTone(value: string): Tone {
  const status = value.toLowerCase();
  if (["passed", "approved", "met"].includes(status)) return "ok";
  if (["passed with conditions", "approved with conditions", "in review", "deferred"].includes(status)) {
    return "warn";
  }
  if (["failed", "not ready", "not met"].includes(status)) return "critical";
  if (["preparing", "ready for review"].includes(status)) return "accent";
  return "neutral";
}

function Findings({
  title,
  findings,
  tone,
}: {
  title: string;
  findings: GateReadinessFinding[];
  tone: "critical" | "warn";
}): JSX.Element | null {
  if (findings.length === 0) return null;
  const Icon = tone === "critical" ? ShieldAlert : AlertTriangle;
  return (
    <section>
      <h3 className="flex items-center gap-1.5 text-meta font-semibold uppercase tracking-wide text-ink-muted">
        <Icon aria-hidden="true" className={cn("h-3.5 w-3.5", tone === "critical" ? "text-critical" : "text-warn")} />
        {title}
      </h3>
      <ul className="mt-2 divide-y divide-line border-y border-line">
        {findings.map((finding) => (
          <li key={`${finding.message}-${finding.source_ids.join("-")}`} className="py-2.5">
            <p className="text-body text-ink">{finding.message}</p>
            <SourceList ids={finding.source_ids} className="mt-1" />
          </li>
        ))}
      </ul>
    </section>
  );
}

function GateDetails({ gate }: { gate: Gate }): JSX.Element {
  const { can } = useAuth();
  const readiness = useGateReadiness(gate.gate_id);
  const criteria = useGateCriteria(gate.gate_id);
  const reviews = useGateReviews(gate.gate_id);
  const transition = useTransitionGate();
  const error = readiness.error ?? criteria.error ?? reviews.error;

  if (error) {
    return (
      <ErrorState
        error={error}
        onRetry={() => {
          void readiness.refetch();
          void criteria.refetch();
          void reviews.refetch();
        }}
      />
    );
  }

  if (readiness.isLoading || criteria.isLoading || reviews.isLoading || !readiness.data) {
    return (
      <div className="space-y-3">
        <LoadingRegion label="Loading Gate readiness" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const result = readiness.data;
  const currentReview = reviews.data?.find(review => review.review_cycle === gate.review_cycle);
  const closeMove: LifecycleMove[] = gate.status === "In Review" && currentReview ? [{
    target: RESULT_FOR_OUTCOME[currentReview.outcome],
    label: `Close as ${RESULT_FOR_OUTCOME[currentReview.outcome]}`,
    from: ["In Review"],
    reasonHint: `Applies review ${currentReview.review_id} (${currentReview.outcome}).`,
  }] : [];
  const canManage = can("work.manage");
  const blocked = result.blockers.length > 0;
  const moves = [...closeMove, ...GATE_MOVES].filter(move => !(blocked && move.target === "Ready for Review"));
  const readyNotice = blocked && gate.status === "Preparing"
    ? `Resolve the ${result.blockers.length === 1 ? "mandatory blocker" : `${result.blockers.length} mandatory blockers`} above before marking this gate ready for review.`
    : undefined;
  return (
    <div className="space-y-6">
      <Findings title="Mandatory blockers" findings={result.blockers} tone="critical" />
      <section>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-meta font-semibold uppercase tracking-wide text-ink-muted">Readiness</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge label={result.state} tone={gateTone(result.state)} />
              {result.percentage === null ? null : (
                <span className="text-section font-semibold text-ink" data-numeric>
                  {result.percentage}%
                </span>
              )}
            </div>
          </div>
          <p className="text-right text-meta text-ink-muted">
            Calculated {formatDateTime(result.calculated_at)}
          </p>
        </div>
        {result.percentage === null ? <p className="mt-3 text-meta text-ink-secondary">Percentage unavailable. Review the configured criteria and required evidence.</p> : (
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-subtle" aria-hidden="true">
            <div
              className={cn("h-full", result.blockers.length > 0 ? "bg-critical" : "bg-ok")}
              style={{ width: `${result.percentage}%` }}
            />
          </div>
        )}
        <dl className="mt-3 grid gap-2 text-body sm:grid-cols-2">
          <div>
            <dt className="text-meta text-ink-muted">Applicable baseline</dt>
            <dd className="mt-0.5 text-ink">{result.applicable_baseline ?? "Not recorded"}</dd>
          </div>
          <div>
            <dt className="text-meta text-ink-muted">Latest human review</dt>
            <dd className="mt-0.5 text-ink">
              {result.latest_review_id
                ? `${result.latest_review_id} · ${result.latest_review_outcome}`
                : "Not recorded"}
            </dd>
          </div>
        </dl>
        {result.evidence_references.length > 0 ? (
          <div className="mt-3">
            <p className="text-meta text-ink-muted">Evidence named in assessments</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-body text-ink">
              {result.evidence_references.map(reference => <li key={reference} className="break-words">{reference}</li>)}
            </ul>
          </div>
        ) : null}
      </section>

      {canManage ? <LifecycleSection key={`${gate.gate_id}-${gate.status}-${gate.review_cycle}`} status={gate.status}
        moves={moves} recordLabel={gate.gate_id} disabled={gate.row_version == null} notice={readyNotice}
        pending={transition.isPending}
        onConfirm={(move, reason) => transition.mutateAsync({ gate, target: move.target as GateStatus, rationale: reason })} /> : null}

      {gate.status === "In Review" && !currentReview ? (can("change.decide")
        ? <GateReviewForm key={`${gate.gate_id}-${gate.review_cycle}`} gate={gate} />
        : <p className="rounded-control border border-line bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">This gate is in review. A person who can decide changes records the outcome.</p>) : null}

      <Findings title="Warnings" findings={result.warnings} tone="warn" />

      <section>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">Criteria</h3>
          {canManage && CONFIGURABLE.includes(gate.status) ? <GateCriterionForm key={gate.gate_id} gate={gate} /> : null}
        </div>
        {!criteria.data || criteria.data.length === 0 ? (
          <p className="mt-2 border-y border-line py-3 text-body text-ink-secondary">
            No criteria have been added to this gate yet.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-line border-y border-line">
            {criteria.data.map((criterion) => (
              <li key={criterion.criterion_id} className="py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{criterion.criterion_name}</p>
                    <p className="mt-0.5 text-meta text-ink-muted">
                      {criterion.criterion_id} · {criterion.criterion_type} · {criterion.is_mandatory ? "Mandatory" : "Optional"}{criterion.evidence_required ? " · Evidence required" : ""}
                    </p>
                  </div>
                  <StatusBadge label={criterion.status} tone={gateTone(criterion.status)} />
                </div>
                <p className="mt-1.5 text-body text-ink-secondary">{criterion.description}</p>
                {criterion.assessment_rationale ? (
                  <p className="mt-1.5 text-meta text-ink-secondary">{criterion.assessment_rationale}{criterion.assessed_by ? ` · ${criterion.assessed_by}` : ""}</p>
                ) : null}
                {criterion.evidence_reference ? (
                  <p className="mt-1.5 break-words text-meta text-ink-secondary"><span className="font-medium text-ink">Evidence:</span> {criterion.evidence_reference}</p>
                ) : null}
                {gate.status === "Preparing" && can("work.update") ? (
                  <div className="mt-2"><GateCriterionAssessment key={`${criterion.criterion_id}-${criterion.status}`} gate={gate} criterion={criterion} /></div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-meta font-semibold uppercase tracking-wide text-ink-muted">Review history</h3>
        {!reviews.data || reviews.data.length === 0 ? (
          <p className="mt-2 border-y border-line py-3 text-body text-ink-secondary">
            No human review has been recorded.
          </p>
        ) : (
          <ol className="mt-2 divide-y divide-line border-y border-line">
            {reviews.data.map((review) => (
              <li key={review.review_id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-ink-muted" />
                    <span className="font-medium text-ink">{review.review_id}</span>
                    <StatusBadge label={review.outcome} tone={gateTone(review.outcome)} />
                  </div>
                  <span className="text-meta text-ink-muted">{formatDateTime(review.reviewed_at)}</span>
                </div>
                <p className="mt-1.5 text-body text-ink-secondary">{review.rationale}</p>
                {review.conditions ? (
                  <p className="mt-1.5 text-meta text-warn">Conditions: {review.conditions}</p>
                ) : null}
                <p className="mt-1 text-meta text-ink-muted">
                  Review cycle {review.review_cycle} · {review.reviewer}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

export function GatesTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const gates = useGates(projectId);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const selected = gates.data?.find(gate => gate.gate_id === selectedId) ?? null;
  const canManage = can("work.manage");
  const columns: Column<Gate>[] = [
    {
      key: "sequence",
      header: "Gate",
      value: (row) => row.sequence,
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.gate_name}</p>
          <p className="text-meta text-ink-muted">
            {row.gate_id} · Sequence {row.sequence}
          </p>
        </div>
      ),
    },
    { key: "owner", header: "Owner", value: (row) => row.owner, cell: (row) => row.owner },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={gateTone(row.status)} />,
    },
    {
      key: "planned",
      header: "Planned review",
      align: "right",
      value: (row) => row.planned_review_date,
      cell: (row) => formatDate(row.planned_review_date),
    },
    {
      key: "actual",
      header: "Actual review",
      align: "right",
      value: (row) => row.actual_review_date ?? "",
      cell: (row) => formatDate(row.actual_review_date),
    },
  ];

  return (
    <>
      {notice ? <p role="status" className="mb-3 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
      <DataTable
        rows={gates.data}
        label="Project gates"
        columns={columns}
        rowKey={(row) => row.gate_id}
        isLoading={gates.isLoading}
        error={gates.isError ? gates.error : undefined}
        onRetry={() => void gates.refetch()}
        onRowClick={(row) => setSelectedId(row.gate_id)}
        searchPlaceholder="Filter Gates"
        emptyTitle="No gates recorded"
        emptyDescription="Gate records appear here once the project's review points are configured."
        emptyAction={canManage ? <Button variant="primary" onClick={() => setCreating(true)}>Create the first gate</Button> : undefined}
        toolbar={canManage ? <Button size="sm" variant="primary" onClick={() => { setNotice(""); setCreating(true); }}><Plus aria-hidden="true" className="h-4 w-4" />New gate</Button> : undefined}
        initialSortKey="sequence"
      />

      <Drawer
        open={selected !== null}
        onClose={() => setSelectedId(null)}
        title={selected?.gate_name ?? "Gate"}
        description={selected ? `${selected.gate_id} · ${selected.status} · Review cycle ${selected.review_cycle}` : undefined}
        width="max-w-3xl"
        footer={<Button onClick={() => setSelectedId(null)}>Close</Button>}
      >
        {selected ? <GateDetails gate={selected} /> : null}
      </Drawer>
      {creating ? <GateFormDrawer projectId={projectId} onClose={() => setCreating(false)}
        onSaved={gate => setNotice(`Gate ${gate.gate_id} created at sequence ${gate.sequence}. Open it to add its criteria.`)} /> : null}
    </>
  );
}