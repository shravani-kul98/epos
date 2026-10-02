import { useState } from "react";
import { Plus } from "lucide-react";
import { AssumptionFormDrawer } from "@/components/governance/assumption-form-drawer";
import { LifecycleSection, type LifecycleMove } from "@/components/governance/lifecycle-section";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useAssumptions, useTransitionAssumption } from "@/lib/queries";
import type { Assumption } from "@/types/api";

// Mirrors the assumption lifecycle the API enforces, so only accepted steps are offered.
const ASSUMPTION_MOVES: readonly LifecycleMove[] = [
  {
    target: "Validated", label: "Validate", from: ["Proposed"], reasonLabel: "Validation evidence",
    reasonHint: "What confirmed it, for example a test report or a supplier confirmation.",
  },
  {
    target: "Invalidated", label: "Invalidate", from: ["Proposed", "Validated"], reasonLabel: "Evidence",
    reasonHint: "What showed it does not hold. Plan the response as a risk, issue or change.", danger: true,
  },
  { target: "Retired", label: "Retire", from: ["Validated", "Invalidated"], reasonHint: "Why it no longer needs tracking." },
  { target: "Proposed", label: "Return to proposed", from: ["Invalidated"], reasonHint: "What changed so it is worth testing again." },
];

export function AssumptionsTab({ projectId }: { projectId:string }): JSX.Element {
  const { can } = useAuth();
  const assumptions=useAssumptions(projectId);
  const transition=useTransitionAssumption();
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const [editingId,setEditingId]=useState<string|null>(null);
  const [creating,setCreating]=useState(false);
  const [notice,setNotice]=useState("");
  const selected=assumptions.data?.find(row=>row.assumption_id===selectedId)??null;
  const editing=assumptions.data?.find(row=>row.assumption_id===editingId)??null;
  const canManage=can("assumption.manage");
  const columns:Column<Assumption>[]=[
    {key:"assumption",header:"Assumption",value:r=>r.assumption_text,cell:r=><div className="max-w-xl"><p className="line-clamp-2 font-medium">{r.assumption_text}</p><p className="mt-1 text-meta text-ink-secondary">{r.assumption_id}</p></div>},
    {key:"owner",header:"Owner",value:r=>r.owner,cell:r=>r.owner},
    {key:"state",header:"Recorded state",value:r=>r.status,cell:r=><StatusBadge label={r.status} tone={statusTone(r.status)}/>},
    {key:"due",header:"Validation due",value:r=>r.validation_due_date??"",cell:r=>formatDate(r.validation_due_date)},
  ];
  return <>
    {notice ? <p role="status" className="mb-3 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
    <DataTable rows={assumptions.data} columns={columns} rowKey={r=>r.assumption_id} label="Project assumptions" searchPlaceholder="Filter assumptions" initialSortKey="due" onRowClick={row=>{setNotice("");setSelectedId(row.assumption_id);}} isLoading={assumptions.isLoading} error={assumptions.error} onRetry={()=>void assumptions.refetch()} emptyTitle="No assumptions recorded" emptyDescription="Only assumptions recorded through the governed workflow appear here. None are inferred from a project score."
      emptyAction={canManage ? <Button variant="primary" onClick={()=>setCreating(true)}>Record the first assumption</Button> : undefined}
      toolbar={canManage ? <Button size="sm" variant="primary" onClick={()=>{setNotice("");setCreating(true);}}><Plus aria-hidden="true" className="h-4 w-4"/>Record assumption</Button> : undefined}/>
    <Drawer open={selected!==null} onClose={()=>setSelectedId(null)} busy={transition.isPending} title="Assumption evidence" description={selected?.assumption_id}>
      {selected ? <div className="space-y-5"><p className="text-section font-medium">{selected.assumption_text}</p><div className="flex flex-wrap items-center gap-2"><StatusBadge label={selected.status} tone={statusTone(selected.status)}/>{canManage ? <Button size="sm" className="ml-auto" onClick={()=>{setEditingId(selected.assumption_id);setSelectedId(null);}}>Edit assumption</Button> : null}</div><dl className="space-y-3">{[
        ["Owner",selected.owner],["Validation due",formatDate(selected.validation_due_date)],
        ["Impact if false",selected.impact_if_false??"Not recorded"],["Validation evidence",selected.validation_evidence??"Not recorded"],
        ["Validated by",selected.validated_by??"Not recorded"],["Validated at",formatDate(selected.validated_at)],
      ].map(([label,value])=><div key={label}><dt className="text-meta text-ink-secondary">{label}</dt><dd className="mt-1 text-body">{value}</dd></div>)}</dl>
      {canManage ? <LifecycleSection key={`${selected.assumption_id}-${selected.status}`} status={selected.status} moves={ASSUMPTION_MOVES} recordLabel={selected.assumption_id}
        disabled={selected.row_version==null} pending={transition.isPending}
        onConfirm={(move,reason)=>transition.mutateAsync({assumption:selected,target:move.target,evidence:reason})}/> : null}
      <SourceList ids={[selected.assumption_id,selected.project_id]}/></div> : null}
    </Drawer>
    {editing ? <AssumptionFormDrawer projectId={projectId} assumption={editing} onClose={()=>{setSelectedId(editing.assumption_id);setEditingId(null);}}/> : null}
    {creating ? <AssumptionFormDrawer projectId={projectId} onClose={()=>setCreating(false)}
      onSaved={assumption=>setNotice(`Assumption ${assumption.assumption_id} recorded as Proposed. Validate it once the evidence is in.`)}/> : null}
  </>;
}