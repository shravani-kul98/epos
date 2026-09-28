import { useState } from "react";
import { RequirementEditAction, RequirementLinks } from "@/components/requirement-verification";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/drawer";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, statusTone, traceTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import type { TraceabilityRow } from "@/types/api";

export function RequirementRegister({ rows, isLoading, error, onRetry, projectId }: {
  rows: TraceabilityRow[] | undefined;
  isLoading: boolean;
  error?: unknown;
  onRetry: () => void;
  /** Maintenance controls appear only inside one project, where its records and members are known. */
  projectId?: string;
}): JSX.Element {
  const { can } = useAuth();
  const manageProject = projectId && can("requirement.manage") ? projectId : null;
  const [selected, setSelected] = useState<TraceabilityRow | null>(null);
  // The drawer follows the latest matrix, so an edit or a new link shows once it is saved.
  const current = selected ? rows?.find(row => row.requirement_id === selected.requirement_id) ?? selected : null;
  const [view, setView] = useState<"matrix" | "explorer">("matrix");
  const columns: Column<TraceabilityRow>[] = [
    {key:"requirement",header:"Requirement",value:r=>`${r.requirement_text} ${r.requirement_id} ${r.project_id}`,cell:r=><div className="min-w-0 max-w-xl"><p className="line-clamp-2 font-medium">{r.requirement_text}</p><p className="mt-1 text-meta text-ink-secondary">{r.requirement_id} · {r.project_id}</p></div>},
    {key:"status",header:"Status",value:r=>r.requirement_status,cell:r=><StatusBadge label={r.requirement_status} tone={statusTone(r.requirement_status)}/>},
    {key:"owner",header:"Owner",value:r=>r.owner??"",cell:r=>r.owner??"Unassigned"},
    {key:"priority",header:"Priority",value:r=>r.priority,cell:r=>r.priority},
    {key:"verification",header:"Verified / linked tests",align:"right",value:r=>r.verified_test_case_ids.length,cell:r=><span data-numeric>{r.verified_test_case_ids.length} / {r.linked_test_case_ids.length}</span>},
    {key:"trace",header:"Trace state",value:r=>r.trace_status,cell:r=><StatusBadge label={r.trace_status} tone={traceTone(r.trace_status)}/>},
  ];
  const projects=[...new Set((rows??[]).map(row=>row.project_id))];
  return <>
    <div role="group" aria-label="Requirements view" className="mb-3 flex flex-wrap gap-2"><Button aria-pressed={view==="matrix"} variant={view==="matrix"?"primary":"secondary"} onClick={()=>setView("matrix")}>Verification matrix</Button><Button aria-pressed={view==="explorer"} variant={view==="explorer"?"primary":"secondary"} onClick={()=>setView("explorer")}>Requirements explorer</Button></div>
    {view==="matrix" || isLoading || error || !rows?.length ? <DataTable label="Requirements" rows={rows} columns={columns} rowKey={r=>r.requirement_id} onRowClick={setSelected} isLoading={isLoading} error={error} onRetry={onRetry} searchPlaceholder="Filter requirements" emptyTitle="No requirements recorded" emptyDescription="Recorded requirements and their test links appear here. Missing evidence is not treated as verification."/> : (
      <div className="space-y-3">{projects.map(projectId=><details open key={projectId} className="disclosure"><summary>Project {projectId} · requirements and recorded test links</summary>
        <ul className="divide-y divide-line px-4">{rows.filter(row=>row.project_id===projectId).map(row=><li key={row.requirement_id} className="py-4">
          <button type="button" onClick={()=>setSelected(row)} className="text-left text-body font-medium text-accent hover:underline">{row.requirement_text}</button>
          <div className="mt-2 flex flex-wrap items-center gap-2"><code>{row.requirement_id}</code><StatusBadge label={row.trace_status} tone={traceTone(row.trace_status)} /></div>
          {row.linked_test_case_ids.length ? <div className="ml-3 mt-3 border-l-2 border-line pl-3"><SourceList ids={row.linked_test_case_ids} label="Linked tests"/></div> : <p className="mt-2 text-meta text-critical">No linked test case is recorded.</p>}
        </li>)}</ul>
      </details>)}</div>
    )}
    <Drawer open={selected!==null} onClose={()=>setSelected(null)} title="Requirement and verification evidence" description={current?.requirement_id} width="max-w-2xl">
      {current ? <div className="space-y-5">
        <p className="text-section font-medium">{current.requirement_text}</p>
        <div className="flex flex-wrap gap-2"><StatusBadge label={current.requirement_status} tone={statusTone(current.requirement_status)}/><StatusBadge label={current.trace_status} tone={traceTone(current.trace_status)}/></div>
        {manageProject ? <RequirementEditAction key={current.requirement_id} projectId={manageProject} requirementId={current.requirement_id} /> : null}
        <dl className="grid grid-cols-2 gap-4"><div><dt className="text-meta text-ink-secondary">Owner</dt><dd>{current.owner??"Unassigned"}</dd></div><div><dt className="text-meta text-ink-secondary">Recorded priority</dt><dd>{current.priority}</dd></div></dl>
        <section><h3 className="text-card font-medium">Verification matrix</h3>
          {current.linked_test_case_ids.length ? <table className="mt-3 w-full text-left text-body"><thead><tr><th scope="col">Test case</th><th scope="col">Evidence state</th></tr></thead><tbody>{current.linked_test_case_ids.map(id=><tr key={id} className="border-t border-line"><td className="py-2"><SourceList ids={[id]} label="Test"/></td><td>{current.verified_test_case_ids.includes(id)?"Verified evidence recorded":"Linked; verification not established"}</td></tr>)}</tbody></table> : <p className="mt-2 text-body text-critical">No verification link is recorded. Review the requirement before relying on coverage.</p>}
        </section>
        {current.open_change_request_ids.length ? <SourceList ids={current.open_change_request_ids} label="Open changes"/> : <p className="text-meta text-ink-secondary">No open changes are linked to this requirement.</p>}
        <SourceList ids={[current.requirement_id,current.project_id]} label="Record context"/>
        {manageProject ? <RequirementLinks key={current.requirement_id} projectId={manageProject} requirementId={current.requirement_id} /> : null}
      </div> : null}
    </Drawer>
  </>;
}