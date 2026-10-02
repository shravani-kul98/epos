import { useState } from "react";
import { Plus } from "lucide-react";
import { IssueFormDrawer } from "@/components/governance/issue-form-drawer";
import { IssueDetail } from "@/components/issue-detail";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { StatusBadge, severityTone, statusTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useIssues } from "@/lib/queries";
import type { Issue } from "@/types/api";

export function IssuesTab({ projectId }: { projectId: string }): JSX.Element {
  const { can } = useAuth();
  const issues = useIssues(projectId);
  const [selectedId,setSelectedId]=useState<string|null>(null);
  const [editingId,setEditingId]=useState<string|null>(null);
  const [creating,setCreating]=useState(false);
  const [notice,setNotice]=useState("");
  const selected = issues.data?.find(issue => issue.issue_id === selectedId) ?? null;
  const editing = issues.data?.find(issue => issue.issue_id === editingId) ?? null;
  const canManage = can("issue.manage");

  const columns: Column<Issue>[] = [
    {
      key: "issue",
      header: "Issue",
      value: (row) => row.title,
      cell: (row) => (
        <div className="min-w-0 max-w-lg">
          <p className="truncate font-medium text-ink">{row.title}</p>
          <p className="text-meta text-ink-secondary">
            {row.issue_id}
            {row.source_reference ? ` · ${row.source_reference}` : ""}
          </p>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      value: (row) => row.severity,
      cell: (row) => <StatusBadge label={row.severity} tone={severityTone(row.severity)} />,
    },
    {
      key: "status",
      header: "Status",
      value: (row) => row.status,
      cell: (row) => <StatusBadge label={row.status} tone={statusTone(row.status)} />,
    },
    {
      key: "owner",
      header: "Owner",
      value: (row) => row.owner ?? "",
      cell: (row) => row.owner ?? "Unassigned",
    },
    {
      key: "raised",
      header: "Raised",
      align: "right",
      value: (row) => row.raised_date,
      cell: (row) => formatDate(row.raised_date),
    },
    {
      key: "target",
      header: "Target resolution",
      align: "right",
      value: (row) => row.target_resolution_date ?? "",
      cell: (row) => formatDate(row.target_resolution_date),
    },
  ];

  return (
    <>
    {notice ? <p role="status" className="mb-3 rounded-card border border-ok/20 bg-ok-tint p-3 text-body">{notice}</p> : null}
    <DataTable
      rows={issues.data ?? []}
      label="Project issues"
      columns={columns}
      rowKey={(row) => row.issue_id}
      onRowClick={(row) => { setNotice(""); setSelectedId(row.issue_id); }}
      isLoading={issues.isLoading}
      error={issues.isError ? issues.error : undefined}
      onRetry={() => void issues.refetch()}
      searchPlaceholder="Filter issues"
      initialSortKey="raised"
      initialSortDirection="desc"
      emptyTitle="No issues recorded"
      emptyDescription="This project has no issues in the register. An issue is a problem that has already materialised; recorded issues appear here with their resolution."
      emptyAction={canManage ? <Button variant="primary" onClick={() => setCreating(true)}>Raise the first issue</Button> : undefined}
      toolbar={canManage ? <Button size="sm" variant="primary" onClick={() => { setNotice(""); setCreating(true); }}><Plus aria-hidden="true" className="h-4 w-4" />Raise issue</Button> : undefined}
    />
    {selected ? <IssueDetail issue={selected} onClose={()=>setSelectedId(null)} onEdit={() => { setEditingId(selected.issue_id); setSelectedId(null); }}/> : null}
    {editing ? <IssueFormDrawer projectId={projectId} issue={editing} onClose={() => { setSelectedId(editing.issue_id); setEditingId(null); }} /> : null}
    {creating ? <IssueFormDrawer projectId={projectId} onClose={() => setCreating(false)}
      onSaved={issue => setNotice(`Issue ${issue.issue_id} raised. Open it to record progress and its resolution.`)} /> : null}
    </>
  );
}
