import { useState } from "react";
import { Plus } from "lucide-react";
import { ActionAssignee } from "@/components/actions/action-assignee";
import { CapacityMatrix } from "@/components/charts/capacity-matrix";
import { ActionFormDrawer, AllocationFormDrawer } from "@/components/governance/team-forms";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Drawer } from "@/components/ui/drawer";
import { Field, Select } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { SourceList } from "@/components/ui/source-list";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useActions, useResources } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { Action, ResourceAllocation } from "@/types/api";

const ACTION_COLUMNS: Column<Action>[] = [
  {
    key: "action",
    header: "Action",
    value: (row) => row.action_description,
    cell: (row) => (
      <div className="min-w-0 max-w-md">
        <p className="truncate font-medium text-ink">{row.action_description}</p>
        <p className="text-meta text-ink-secondary">
          {row.action_id}
          {row.source_reference ? ` · from ${row.source_reference}` : ""}
        </p>
      </div>
    ),
  },
  { key: "owner", header: "Owner", value: (row) => row.owner ?? "", cell: (row) => row.owner ?? "Unassigned" },
  {
    key: "status",
    header: "Status",
    value: (row) => row.status,
    cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
  },
  { key: "priority", header: "Priority", value: (row) => row.priority, cell: (row) => row.priority },
  {
    key: "due",
    header: "Due",
    align: "right",
    value: (row) => row.due_date,
    cell: (row) => formatDate(row.due_date),
  },
];

export function TeamTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const resources = useResources(projectId);
  const actions = useActions(projectId);
  const { params, update, clear } = useViewParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState<"action" | "allocation" | null>(null);
  const [notice, setNotice] = useState("");
  const selected = actions.data?.find(action => action.action_id === selectedId) ?? null;
  const canAllocate = can("work.manage");
  const canAct = can("action.manage");
  const actionRows=actions.data?.filter(action=>(!params.get("owner")||action.owner===params.get("owner"))&&(!params.get("action_state")||action.status===params.get("action_state")));

  const overallocated = (resources.data ?? []).filter((row: ResourceAllocation) => row.is_overallocated);

  return (
    <div className="space-y-4">
      {notice ? <p role="status" className="rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
      <Card>
        <CardHeader
          title="Capacity"
          description="Allocated against available hours, from the stored weekly records"
          action={
            <div className="flex flex-wrap items-center gap-2">
              {overallocated.length > 0 ? (
                <StatusBadge label={`${overallocated.length} over capacity`} tone="critical" />
              ) : null}
              {canAllocate ? <Button size="sm" onClick={() => { setNotice(""); setCreating("allocation"); }}><Plus aria-hidden="true" className="h-4 w-4" />Record allocation</Button> : null}
            </div>
          }
        />
        {resources.isError ? <ErrorState error={resources.error} onRetry={()=>void resources.refetch()}/> : resources.isLoading ? (
          <CardBody>
            <SkeletonTable rows={3}/>
          </CardBody>
        ) : !resources.data || resources.data.length === 0 ? (
          <EmptyState
            title="No capacity records"
            description="Weekly allocation records feed the team capacity factor of the health score."
            className="py-8"
          />
        ) : (
          <CardBody>
            <CapacityMatrix records={resources.data}/>
          </CardBody>
        )}
      </Card>

      <FilterBar description="Action tracker" active={Boolean(params.get("owner")||params.get("action_state"))} onClear={()=>clear(["owner","action_state"])}>
        <Field label="Action owner" htmlFor="action-owner-filter"><Select id="action-owner-filter" value={params.get("owner")??""} onChange={e=>update({owner:e.target.value})}><option value="">All owners</option>{[...new Set((actions.data??[]).map(action=>action.owner).filter((owner):owner is string=>Boolean(owner)))].sort().map(owner=><option key={owner}>{owner}</option>)}</Select></Field>
        <Field label="Action state" htmlFor="action-state-filter"><Select id="action-state-filter" value={params.get("action_state")??""} onChange={e=>update({action_state:e.target.value})}><option value="">All recorded states</option>{[...new Set((actions.data??[]).map(action=>action.status))].sort().map(status=><option key={status}>{status}</option>)}</Select></Field>
      </FilterBar>
      <DataTable
        rows={actionRows}
        label="Action tracker"
        initialSortKey="due"
        onRowClick={row => setSelectedId(row.action_id)}
        columns={ACTION_COLUMNS}
        rowKey={(row) => row.action_id}
        isLoading={actions.isLoading}
        error={actions.isError ? actions.error : undefined}
        onRetry={() => void actions.refetch()}
        searchPlaceholder="Filter actions"
        emptyTitle="No actions recorded"
        emptyDescription="Actions agreed in reviews are tracked here and feed the follow-through factor."
        toolbar={canAct ? <Button size="sm" variant="primary" onClick={() => { setNotice(""); setCreating("action"); }}><Plus aria-hidden="true" className="h-4 w-4" />New action</Button> : undefined}
      />
      <Drawer open={selected!==null} onClose={()=>setSelectedId(null)} title="Action record" description={selected?.action_id}>
        {selected ? <div className="space-y-4"><p className="text-section font-medium">{selected.action_description}</p><StatusBadge label={selected.status} tone={statusTone(selected.status)}/><dl className="grid grid-cols-2 gap-4"><div><dt className="text-meta text-ink-secondary">Owner</dt><dd>{selected.owner??"Unassigned"}</dd></div><div><dt className="text-meta text-ink-secondary">Due date</dt><dd>{formatDate(selected.due_date)}</dd></div><div><dt className="text-meta text-ink-secondary">Recorded priority</dt><dd>{selected.priority}</dd></div><div><dt className="text-meta text-ink-secondary">Source reference</dt><dd>{selected.source_reference??"Not recorded"}</dd></div></dl><ActionAssignee key={selected.action_id} action={selected}/><SourceList ids={[selected.action_id,selected.project_id]}/></div> : null}
      </Drawer>
      {creating === "action" ? <ActionFormDrawer projectId={projectId} onClose={() => setCreating(null)}
        onSaved={action => setNotice(`Action ${action.action_id} created${action.owner ? ` for ${action.owner}` : ""}.`)} /> : null}
      {creating === "allocation" ? <AllocationFormDrawer projectId={projectId} onClose={() => setCreating(null)}
        onSaved={allocation => setNotice(`Recorded ${allocation.allocated_hours} of ${allocation.capacity_hours} hours for ${allocation.resource_name}, week of ${formatDate(allocation.week_start_date)}.`)} /> : null}
    </div>
  );
}
