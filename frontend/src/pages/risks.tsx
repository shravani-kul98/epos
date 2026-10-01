import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { RiskHeatmap } from "@/components/charts/risk-heatmap";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Select } from "@/components/ui/form";
import { Field } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import { SourceList } from "@/components/ui/source-list";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, statusTone } from "@/components/ui/status-badge";
import { formatDate } from "@/lib/format";
import { usePortfolio, useRiskRegister } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { Risk } from "@/types/api";

export function RisksPage(): JSX.Element {
  const portfolio = usePortfolio();
  const projects = useMemo(() => portfolio.data?.projects ?? [], [portfolio.data]);
  const { params, update, clear } = useViewParams();
  const projectId = params.get("project") ?? "";
  const [selectedRisk, setSelectedRisk] = useState<Risk | null>(null);
  const cell = params.has("probability") && params.has("impact") ? [Number(params.get("probability")), Number(params.get("impact"))] as const : null;

  const risks = useRiskRegister(projectId || undefined);

  const allRows = risks.data ?? [];
  const rows = allRows.filter(risk => (!cell || (risk.probability === cell[0] && risk.impact === cell[1])) && (!params.get("status") || risk.status === params.get("status")));
  const open = allRows.filter((risk) => risk.status.toLowerCase() !== "closed");
  const unowned = open.filter(risk => !risk.mitigation_owner);
  const overdue = open.filter((risk) => {
    const asOf = portfolio.data?.as_of_date;
    return asOf ? risk.due_date < asOf : false;
  });

  const columns: Column<(typeof rows)[number]>[] = [
    {
      key: "risk",
      header: "Risk",
      value: (row) => row.risk_name,
      cell: (row) => (
        <div className="min-w-0 max-w-md">
          <p className="truncate font-medium text-ink">{row.risk_name}</p>
          <p className="text-meta text-ink-secondary">
            {row.risk_id} ·{" "}
            <Link to={`/projects/${row.project_id}?tab=risks`} className="text-accent hover:underline">
              {row.project_id}
            </Link>
          </p>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      align: "right",
      value: (row) => row.severity_score,
      cell: (row) => (
        <span className="text-ink" data-numeric>
          {row.severity_score}
        </span>
      ),
    },
    {
      key: "probability",
      header: "Probability",
      align: "right",
      value: (row) => row.probability,
      cell: (row) => <span data-numeric>{row.probability}</span>,
    },
    {
      key: "impact",
      header: "Impact",
      align: "right",
      value: (row) => row.impact,
      cell: (row) => <span data-numeric>{row.impact}</span>,
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
      key: "due",
      header: "Due",
      align: "right",
      value: (row) => row.due_date,
      cell: (row) => formatDate(row.due_date),
    },
  ];

  return (
    <>
      <PageHeader
        title="Risks"
        description="The risk register, with severity as recorded by EPOS from probability and impact."
        scope={projects.find(project=>project.project_id===projectId)?.project_name ?? "All accessible projects"}
        actions={
          projectId ? (
            <Link to={`/projects/${projectId}?tab=risks`}>
              <span className="text-meta font-medium text-accent hover:underline">Open in project</span>
            </Link>
          ) : null
        }
      />

      <FilterBar active={Boolean(projectId || cell || params.get("status") || params.get("q"))} onClear={()=>clear(["project","probability","impact","status","q"])}>
        <Field label="Project" htmlFor="risk-project">
        <Select
          id="risk-project"
          value={projectId}
          onChange={(event) => update({project:event.target.value,probability:undefined,impact:undefined})}
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.project_id} — {project.project_name}
            </option>
          ))}
        </Select>
        </Field>
        <Field label="Status" htmlFor="risk-status"><Select id="risk-status" value={params.get("status") ?? ""} onChange={e=>update({status:e.target.value})}><option value="">All recorded states</option>{[...new Set(allRows.map(risk=>risk.status))].sort().map(status=><option key={status}>{status}</option>)}</Select></Field>
        {cell ? <p className="text-meta text-ink-secondary">Matrix selection: probability {cell[0]}, impact {cell[1]}.</p> : null}
      </FilterBar>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Open risks" value={risks.data ? open.length : "—"} caption="Not yet closed in the project scope" />
        <MetricCard
          label="Unassigned owners"
          value={risks.data ? unowned.length : "—"}
          caption="Open risk records with no mitigation owner"
        />
        <MetricCard label="Past due" value={risks.data ? overdue.length : "—"} caption="Mitigation date already passed" />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DataTable
            rows={rows}
            label="Risk register"
            onRowClick={setSelectedRisk}
            filterValue={params.get("q") ?? ""}
            onFilterChange={q=>update({q})}
            columns={columns}
            rowKey={(row) => row.risk_id}
            isLoading={risks.isLoading}
            error={risks.isError ? risks.error : undefined}
            onRetry={() => void risks.refetch()}
            searchPlaceholder="Filter risks"
            initialSortKey="severity"
            initialSortDirection="desc"
            emptyTitle="No risks recorded"
            emptyDescription={
              projectId
                ? "This project has no risks in the register."
                : "No project in this workspace has a risk in the register."
            }
          />
        </div>
        <Card className="h-fit">
          <CardHeader title="Probability and impact" />
          <CardBody>
            <RiskHeatmap risks={open} selectedCell={cell} onSelectCell={(probability,impact)=>update(cell?.[0]===probability&&cell[1]===impact ? {probability:undefined,impact:undefined} : {probability:String(probability),impact:String(impact)})} />
          </CardBody>
        </Card>
      </div>
      <Drawer open={selectedRisk!==null} onClose={()=>setSelectedRisk(null)} title={selectedRisk?.risk_name ?? "Risk record"} description="Stored risk assessment; no severity is estimated in the browser." footer={selectedRisk ? <Link to={`/projects/${selectedRisk.project_id}?tab=risks`}><Button variant="primary">Open project risk register</Button></Link> : undefined}>
        {selectedRisk ? <>
          <dl className="grid grid-cols-2 gap-4">{[
            ["Recorded severity",selectedRisk.severity_score], ["Status",selectedRisk.status],
            ["Probability",selectedRisk.probability], ["Impact",selectedRisk.impact],
            ["Mitigation owner",selectedRisk.mitigation_owner ?? "Unassigned"],
            ["Due",formatDate(selectedRisk.due_date)], ["Mitigation",selectedRisk.mitigation_status ?? "Not recorded"],
          ].map(([label,value])=><div key={label}><dt className="text-meta text-ink-secondary">{label}</dt><dd className="mt-1 text-body" data-numeric>{value}</dd></div>)}</dl>
          <SourceList ids={[selectedRisk.risk_id,selectedRisk.project_id]} className="mt-5" />
        </> : null}
      </Drawer>
    </>
  );
}
