import { useState } from "react";
import { Plus } from "lucide-react";

import { RecordOwnerField } from "@/components/record-owner-field";
import { RiskHeatmap, RiskHeatmapLegend } from "@/components/charts/risk-heatmap";
import { RiskFormDrawer } from "@/components/governance/risk-form-drawer";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select, TextArea, TextInput } from "@/components/ui/form";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { ApiError, useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useRisks, useUpdateRisk } from "@/lib/queries";
import type { Risk } from "@/types/api";

// The vocabulary the API accepts. Closed and Accepted end a risk's scored exposure.
const RISK_STATUSES: readonly string[] = ["Open", "Mitigating", "Closed", "Accepted"];
const ENDING_STATUSES: readonly string[] = ["Closed", "Accepted"];
const MITIGATION_STATUSES: readonly string[] = ["Not Started", "In Progress", "Complete", "Not Required"];
// A risk is closed only once nothing is left to mitigate; the API refuses anything else.
const CLOSING_MITIGATION_STATUSES: readonly string[] = ["Complete", "Not Required"];
const LEVELS = [1, 2, 3, 4, 5];

/** A recorded value in the spelling EPOS uses, or unchanged when EPOS does not recognise it. */
function canonical(value: string | null | undefined, options: readonly string[]): string {
  if (!value) return "";
  return options.find((option) => option.toLowerCase() === value.trim().toLowerCase()) ?? value;
}

/** The choices, plus an unrecognised recorded value so the form never misstates what is stored. */
function choicesWith(value: string | null | undefined, options: readonly string[]): string[] {
  const current = canonical(value, options);
  return current && !options.includes(current) ? [...options, current] : [...options];
}

function isLive(risk: Risk): boolean {
  return !ENDING_STATUSES.includes(canonical(risk.status, RISK_STATUSES));
}

export function RisksTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const risks = useRisks(projectId);
  const updateRisk = useUpdateRisk(projectId);
  const [editing, setEditing] = useState<Risk | null>(null);
  const [draft, setDraft] = useState<Partial<Risk>>({});
  const [rationale, setRationale] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string,string>>({});
  const [cell,setCell] = useState<readonly [number,number] | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");

  const editable = can("risk.manage");
  const chosenStatus = editing ? canonical(draft.status ?? editing.status, RISK_STATUSES) : "";
  const endsManagement =
    editing !== null &&
    ENDING_STATUSES.includes(chosenStatus) &&
    chosenStatus !== canonical(editing.status, RISK_STATUSES);
  const closing = endsManagement && chosenStatus === "Closed";
  const chosenMitigation = canonical(draft.mitigation_status, MITIGATION_STATUSES);

  function openEditor(risk: Risk): void {
    setNotice("");
    setEditing(risk);
    setRationale("");
    setSaveError(null);
    setFieldErrors({});
    setDraft({
      probability: risk.probability,
      impact: risk.impact,
      status: risk.status,
      mitigation_owner: risk.mitigation_owner,
      mitigation_status: risk.mitigation_status,
      due_date: risk.due_date,
    });
  }

  async function save(): Promise<void> {
    if (!editing || editing.row_version == null) return;
    setSaveError(null);
    setFieldErrors({});
    if (endsManagement && !rationale.trim()) {
      setFieldErrors({ rationale: `Record why this risk is being marked ${chosenStatus}.` });
      return;
    }
    if (closing && !CLOSING_MITIGATION_STATUSES.includes(chosenMitigation)) {
      setFieldErrors({ mitigation_status: "Set the mitigation to Complete or Not Required before closing the risk." });
      return;
    }
    // Only what the reviewer changed is sent, so an untouched legacy value is never re-validated.
    const changes = Object.fromEntries(
      Object.entries(draft).filter(([key, value]) => value !== editing[key as keyof Risk]),
    ) as Partial<Risk>;
    try {
      await updateRisk.mutateAsync({
        riskId: editing.risk_id,
        patch: {
          ...changes,
          ...(endsManagement ? { rationale: rationale.trim() } : {}),
          row_version: editing.row_version,
        },
      });
      setEditing(null);
    } catch (caught) {
      if(caught instanceof ApiError) setFieldErrors(caught.fieldErrors);
      setSaveError(caught instanceof ApiError ? caught.message : "The risk could not be saved.");
    }
  }

  const columns: Column<Risk>[] = [
    {
      key: "risk",
      header: "Risk",
      value: (row) => row.risk_name,
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.risk_name}</p>
          <p className="text-meta text-ink-secondary">{row.risk_id}</p>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      align: "right",
      // Live risks sort ahead of closed and accepted ones, which no longer carry exposure.
      value: (row) => (isLive(row) ? 1000 : 0) + row.severity_score,
      cell: (row) => (
        <div className="flex items-center justify-end gap-2">
          <span data-numeric>{row.severity_score}</span>
          <StatusBadge
            label={`P${row.probability} × I${row.impact}`}
            tone="neutral"
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
    },
    {
      key: "owner",
      header: "Mitigation owner",
      value: (row) => row.mitigation_owner ?? "",
      cell: (row) => row.mitigation_owner ?? "Unassigned",
    },
    {
      key: "mitigation",
      header: "Mitigation",
      value: (row) => row.mitigation_status ?? "",
      cell: (row) => row.mitigation_status ?? "Not recorded",
    },
    {
      key: "due",
      header: "Due",
      align: "right",
      value: (row) => row.due_date,
      cell: (row) => formatDate(row.due_date),
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 2xl:grid-cols-3">
      {notice ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body 2xl:col-span-3">{notice}</p> : null}
      <div className="min-w-0 2xl:col-span-2">
        {cell ? (
          <p role="status" className="mb-3 flex flex-wrap items-center gap-2 rounded-control border border-accent-border bg-accent-tint px-3 py-2 text-meta text-ink">
            Showing live risks with probability {cell[0]} and impact {cell[1]} from the heatmap.
            <Button size="sm" variant="ghost" onClick={() => setCell(null)}>Clear filter</Button>
          </p>
        ) : null}
        <DataTable
          rows={risks.data?.filter(risk=>!cell || (isLive(risk)&&risk.probability===cell[0]&&risk.impact===cell[1]))}
          label="Project risks"
          columns={columns}
          rowKey={(row) => row.risk_id}
          isLoading={risks.isLoading}
          error={risks.isError ? risks.error : undefined}
          onRetry={() => void risks.refetch()}
          onRowClick={editable ? openEditor : undefined}
          searchPlaceholder="Filter risks"
          initialSortKey="severity"
          initialSortDirection="desc"
          emptyTitle="No risks recorded"
          emptyDescription="A project with no recorded risks reduces reporting confidence rather than improving health."
          emptyAction={editable && !cell ? <Button variant="primary" onClick={() => setCreating(true)}>Record the first risk</Button> : undefined}
          toolbar={editable ? <Button size="sm" variant="primary" onClick={() => { setNotice(""); setCreating(true); }}><Plus aria-hidden="true" className="h-4 w-4" />New risk</Button> : undefined}
        />
      </div>

      <Card className="h-fit">
        <CardHeader title="Probability and impact" description="Where this project's risks sit" />
        <CardBody>
          <RiskHeatmap risks={(risks.data ?? []).filter(isLive)} selectedCell={cell} onSelectCell={(probability,impact)=>setCell(cell?.[0]===probability&&cell[1]===impact?null:[probability,impact])} />
          <div className="mt-3">
            <RiskHeatmapLegend />
          </div>
        </CardBody>
      </Card>

      <Drawer
        open={editing !== null}
        dirty={editing!==null&&(rationale.trim()!==""||Object.entries(draft).some(([key,value])=>value!==editing[key as keyof Risk]))}
        busy={updateRisk.isPending}
        onClose={() => setEditing(null)}
        title={editing?.risk_name ?? "Risk"}
        description={
          editing ? `${editing.risk_id} · severity is recalculated by EPOS from probability and impact` : undefined
        }
        footer={(close) =>
          <>
            <Button onClick={close}>Cancel</Button>
            <Button variant="primary" onClick={() => void save()} disabled={updateRisk.isPending || editing?.row_version==null}>
              {updateRisk.isPending ? "Saving" : "Save changes"}
            </Button>
          </>
        }
      >
        {editing ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Probability" htmlFor="risk-probability" hint="1 is unlikely, 5 is near certain." error={fieldErrors.probability}>
                <Select
                  id="risk-probability"
                  value={String(draft.probability ?? editing.probability)}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, probability: Number(event.target.value) }))
                  }
                >
                  {LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Impact" htmlFor="risk-impact" hint="1 is minor, 5 is severe." error={fieldErrors.impact}>
                <Select
                  id="risk-impact"
                  value={String(draft.impact ?? editing.impact)}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, impact: Number(event.target.value) }))
                  }
                >
                  {LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field label="Status" htmlFor="risk-status" error={fieldErrors.status}>
              <Select
                id="risk-status"
                value={chosenStatus}
                onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}
              >
                {choicesWith(editing.status, RISK_STATUSES).map((status) => (
                  <option key={status} value={status} disabled={!RISK_STATUSES.includes(status)}>
                    {status}
                  </option>
                ))}
              </Select>
            </Field>

            {endsManagement ? (
              <Field
                label="Reason"
                htmlFor="risk-rationale"
                hint={`${chosenStatus} ends this risk's scored exposure, so the reason is kept in the audit trail.`}
                error={fieldErrors.rationale}
              >
                <TextArea
                  id="risk-rationale"
                  rows={3}
                  value={rationale}
                  onChange={(event) => setRationale(event.target.value)}
                />
              </Field>
            ) : null}

            <RecordOwnerField
              key={editing.risk_id}
              projectId={projectId}
              purpose="risk"
              label="Mitigation owner"
              id="risk-owner"
              value={draft.mitigation_owner ?? null}
              userId={draft.mitigation_owner_user_id !== undefined ? draft.mitigation_owner_user_id : editing.mitigation_owner_user_id ?? null}
              linksAccount
              error={fieldErrors.mitigation_owner ?? fieldErrors.mitigation_owner_user_id}
              onChange={(name, userId) => setDraft((current) => ({ ...current, mitigation_owner: name, mitigation_owner_user_id: userId }))}
            />

            <Field label="Mitigation status" htmlFor="risk-mitigation" error={fieldErrors.mitigation_status}
              hint={closing ? "A risk is closed once its mitigation is complete or no longer needed." : undefined}>
              <Select
                id="risk-mitigation"
                value={chosenMitigation}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, mitigation_status: event.target.value || null }))
                }
              >
                <option value="" disabled={closing}>Not recorded</option>
                {choicesWith(editing.mitigation_status, MITIGATION_STATUSES).map((status) => (
                  <option key={status} value={status}
                    disabled={!MITIGATION_STATUSES.includes(status) || (closing && !CLOSING_MITIGATION_STATUSES.includes(status))}>
                    {status}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Due date" htmlFor="risk-due" error={fieldErrors.due_date}>
              <TextInput
                id="risk-due"
                type="date"
                value={draft.due_date ?? editing.due_date}
                onChange={(event) => setDraft((current) => ({ ...current, due_date: event.target.value }))}
              />
            </Field>

            {saveError ? (
              <p className="rounded-md border border-critical/20 bg-critical-tint px-3 py-2 text-meta text-critical" role="alert">
                {saveError}
              </p>
            ) : null}
          </div>
        ) : null}
      </Drawer>
      {creating ? <RiskFormDrawer projectId={projectId} onClose={() => setCreating(false)}
        onSaved={risk => setNotice(`Risk ${risk.risk_id} recorded with severity ${risk.severity_score}.`)} /> : null}
    </div>
  );
}
