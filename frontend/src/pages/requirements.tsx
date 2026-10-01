import { RequirementRegister } from "@/components/requirement-register";
import { Select } from "@/components/ui/form";
import { Field } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { formatPercent } from "@/lib/format";
import { usePortfolio, useTraceability } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";

export function RequirementsPage(): JSX.Element {
  const portfolio = usePortfolio();
  const { params, update, clear } = useViewParams();
  const projectId = params.get("project") ?? "";
  const traceability = useTraceability(projectId || undefined);
  const data = traceability.data;

  return (
    <>
      <PageHeader
        title="Requirements"
        description="Traceability from each requirement through to the tests that verify it."
        scope={portfolio.data?.projects.find(project=>project.project_id===projectId)?.project_name ?? "All accessible projects"}
        asOfDate={data?.as_of_date}
      />

      <FilterBar active={Boolean(projectId)} onClear={()=>clear(["project"])} description="Requirement scope">
        <Field label="Project" htmlFor="req-project">
        <Select id="req-project" value={projectId} onChange={(event) => update({project:event.target.value})}>
          <option value="">All projects</option>
          {(portfolio.data?.projects ?? []).map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.project_id} — {project.project_name}
            </option>
          ))}
        </Select>
        </Field>
      </FilterBar>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <MetricCard label="Requirements" value={data?.total_requirements ?? "—"} caption="In the current scope" />
        <MetricCard
          label="Verified coverage"
          value={data ? formatPercent(data.coverage_percent) : "—"}
          caption="Have at least one verified linked test"
        />
        <MetricCard
          label="Uncovered"
          value={data ? data.rows.filter((row) => row.linked_test_case_ids.length === 0).length : "—"}
          caption="No linked test case at all"
        />
      </div>

      <div className="mt-4">
        <RequirementRegister
          rows={data?.rows}
          isLoading={traceability.isLoading}
          error={traceability.isError ? traceability.error : undefined}
          onRetry={() => void traceability.refetch()}
        />
      </div>
    </>
  );
}
