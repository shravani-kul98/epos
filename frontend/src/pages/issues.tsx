import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DistributionBars } from "@/components/charts/distribution-bars";
import { IssueDetail } from "@/components/issue-detail";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Select } from "@/components/ui/form";
import { Field } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, severityTone, statusTone } from "@/components/ui/status-badge";
import { formatDate } from "@/lib/format";
import { useIssues, usePortfolio } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { Issue } from "@/types/api";

const RESOLVED_STATES = new Set(["Resolved", "Closed"]);

const SEVERITY_COLOURS: Record<string, string> = {
  Critical: "var(--critical)",
  High: "var(--advisory)",
  Medium: "var(--warn)",
  Low: "var(--accent)",
};

export function IssuesPage(): JSX.Element {
  const portfolio = usePortfolio();
  const projects = useMemo(() => portfolio.data?.projects ?? [], [portfolio.data]);
  const { params, update, clear }=useViewParams();
  const projectId=params.get("project")??"";
  const [selectedId,setSelectedId]=useState<string|null>(null);

  const issues = useIssues(projectId || undefined);
  const rows = issues.data ?? [];
  const selected = rows.find(issue => issue.issue_id === selectedId) ?? null;
  const open = rows.filter((issue) => !RESOLVED_STATES.has(issue.status));
  const critical = open.filter((issue) => issue.severity === "Critical");
  const asOf = portfolio.data?.as_of_date;
  const overdue = open.filter(
    (issue) => asOf !== undefined && issue.target_resolution_date !== null && issue.target_resolution_date < asOf,
  );

  const severities = ["Critical", "High", "Medium", "Low"].map((name) => ({
    name,
    value: open.filter((issue) => issue.severity === name).length,
    colour: SEVERITY_COLOURS[name],
  }));

  const columns: Column<Issue>[] = [
    {
      key: "issue",
      header: "Issue",
      value: (row) => row.title,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-medium text-ink">{row.title}</p>
          <p className="text-meta text-ink-secondary">
            {row.issue_id} ·{" "}
            <Link to={`/projects/${row.project_id}?tab=issues`} className="text-accent hover:underline">
              {row.project_id}
            </Link>
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
      <PageHeader
        title="Issues"
        description="Problems that have already happened, as recorded against each project. A risk that materialises belongs here."
        scope={projects.find(project=>project.project_id===projectId)?.project_name??"All accessible projects"}
        actions={
          projectId ? (
            <Link to={`/projects/${projectId}?tab=issues`}>
              <span className="text-meta font-medium text-accent hover:underline">Open in project</span>
            </Link>
          ) : null
        }
      />

      <FilterBar active={Boolean(projectId||params.get("severity"))} onClear={()=>clear(["project","severity"])} description="Issue register view">
        <Field htmlFor="issue-project" label="Project">
        <Select id="issue-project" value={projectId} onChange={(event) => update({project:event.target.value})}>
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.project_id} — {project.project_name}
            </option>
          ))}
        </Select>
        </Field>
        <Field htmlFor="issue-severity" label="Severity"><Select id="issue-severity" value={params.get("severity")??""} onChange={e=>update({severity:e.target.value})}><option value="">All severities</option>{Object.keys(SEVERITY_COLOURS).map(severity=><option key={severity}>{severity}</option>)}</Select></Field>
      </FilterBar>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Open issues" value={issues.data?open.length:"—"} caption="Not yet resolved or closed in the project scope" />
        <MetricCard label="Critical" value={issues.data?critical.length:"—"} caption="Recorded at critical severity" />
        <MetricCard label="Past target" value={issues.data?overdue.length:"—"} caption="Target resolution date already passed" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DataTable
            rows={rows.filter(issue=>!params.get("severity")||issue.severity===params.get("severity"))}
            onRowClick={row => setSelectedId(row.issue_id)}
            label="Issue register"
            columns={columns}
            rowKey={(row) => row.issue_id}
            isLoading={issues.isLoading}
            error={issues.isError ? issues.error : undefined}
            onRetry={() => void issues.refetch()}
            searchPlaceholder="Filter issues"
            initialSortKey="raised"
            initialSortDirection="desc"
            emptyTitle="No issues recorded"
            emptyDescription={
              projectId
                ? "This project has no issues in the register."
                : "No project in this workspace has an issue in the register."
            }
          />
        </div>
        <Card className="h-fit">
          <CardHeader title="Open issues by severity" description="Recorded severity, not calculated" />
          <CardBody>
            <DistributionBars unit="issues" data={severities} preserveOrder onSelect={severity=>update({severity:params.get("severity")===severity?undefined:severity})} />
          </CardBody>
        </Card>
      </div>
      {selected ? <IssueDetail issue={selected} onClose={()=>setSelectedId(null)}/> : null}
    </>
  );
}
