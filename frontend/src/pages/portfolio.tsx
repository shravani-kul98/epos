import { Link } from "react-router-dom";

import { BandDonut } from "@/components/charts/band-donut";
import { DistributionBars } from "@/components/charts/distribution-bars";
import { HealthConfidenceScatter } from "@/components/charts/health-confidence-scatter";
import { ProjectHealthBars } from "@/components/charts/project-health-bars";
import { BAND_COLOURS, CONFIDENCE_COLOURS } from "@/lib/chart-theme";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { ErrorState } from "@/components/ui/error-state";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Field, Select, TextInput } from "@/components/ui/form";
import { FilterBar } from "@/components/ui/filter-bar";
import { MethodologyPopover } from "@/components/ui/methodology-popover";
import { TermHelp } from "@/components/ui/term-help";
import { LoadingRegion, SkeletonCards } from "@/components/ui/loading-skeleton";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, confidenceTone, healthTone, severityTone } from "@/components/ui/status-badge";
import { formatDate, formatScore } from "@/lib/format";
import { usePortfolio, usePortfolioView, type PortfolioViewFilters } from "@/lib/queries";
import { useViewParams } from "@/lib/view-params";
import type { ProjectSummary } from "@/types/api";

const COLUMNS: Column<ProjectSummary>[] = [
  {
    key: "project",
    header: "Project",
    value: (row) => row.project_name,
    cell: (row) => (
      <div className="min-w-0">
        <Link to={`/projects/${row.project_id}`} className="font-medium text-ink hover:text-accent">
          {row.project_name}
        </Link>
        <p className="text-meta text-ink-secondary">
          {row.project_id} · {row.domain}
        </p>
      </div>
    ),
  },
  { key: "manager", header: "Manager", value: (row) => row.project_manager, cell: (row) => row.project_manager },
  { key: "phase", header: "Phase", value: (row) => row.project_phase, cell: (row) => row.project_phase },
  {
    key: "health",
    header: "Health",
    align: "right",
    value: (row) => row.assessment?.is_assessed === false ? "" : row.health_score,
    cell: (row) => row.assessment?.is_assessed === false ? <span className="text-meta text-ink-secondary" title={row.assessment.reason}>Not yet assessed</span> : (
      <div className="flex items-center justify-end gap-2">
        <span data-numeric>{formatScore(row.health_score)}</span>
        <StatusBadge label={row.health_band} tone={healthTone(row.health_band)} />
      </div>
    ),
  },
  {
    key: "confidence",
    header: "Confidence",
    align: "right",
    value: (row) => row.assessment?.is_assessed === false ? "" : row.confidence_score,
    cell: (row) => row.assessment?.is_assessed === false ? <span className="text-meta text-ink-secondary">Not yet assessed</span> : (
      <div className="flex items-center justify-end gap-2">
        <span data-numeric>{formatScore(row.confidence_score)}</span>
        <StatusBadge label={row.confidence_band} tone={confidenceTone(row.confidence_band)} />
      </div>
    ),
  },
  {
    key: "alerts",
    header: "Open alerts",
    align: "right",
    value: (row) => row.open_alert_count,
    cell: (row) => (
      <span data-numeric className={row.critical_alert_count > 0 ? "font-semibold text-critical" : "text-ink"}>
        {row.open_alert_count}
        {row.critical_alert_count > 0 ? ` (${row.critical_alert_count} critical)` : ""}
      </span>
    ),
  },
  {
    key: "forecast",
    header: "Forecast end",
    align: "right",
    value: (row) => row.forecast_end_date ?? "",
    cell: (row) => formatDate(row.forecast_end_date),
  },
];

const FILTER_KEYS = ["project_id", "health_band", "confidence_band", "domain", "manager", "phase", "priority", "alert_severity", "forecast_after", "forecast_before", "needs_attention"] as const;

export function PortfolioPage(): JSX.Element {
  const base = usePortfolio();
  const { params, update, clear } = useViewParams();
  const filters: PortfolioViewFilters = Object.fromEntries(FILTER_KEYS.map(key => [key, params.get(key) || undefined]));
  const portfolio = usePortfolioView(filters);
  const data = portfolio.data;
  const projects = base.data?.projects ?? [];
  const isFiltered = FILTER_KEYS.some(key => Boolean(filters[key]));
  const clearFilters = () => clear([...FILTER_KEYS, "q"]);
  const toggle = (key: typeof FILTER_KEYS[number], value: string) => update({ [key]: filters[key] === value ? undefined : value });
  const options = (key: "project_manager" | "domain" | "project_phase" | "business_priority") => [...new Set(projects.map(project => project[key]))].sort();

  return (
    <>
      <PageHeader
        title="Portfolio"
        description="Compare delivery position, find concentrations of concern, and open the work behind them."
        scope={isFiltered ? "Filtered portfolio · shareable view" : "All accessible projects"}
        asOfDate={data?.as_of_date}
      />
      <div className="mb-4 flex flex-wrap gap-4"><TermHelp term="health" /><TermHelp term="confidence" /></div>
      {data?.unassessed_count ? <p className="mb-4 rounded-card border border-line bg-surface-subtle p-3 text-body">{data.unassessed_count} {data.unassessed_count === 1 ? "project is" : "projects are"} not yet assessed. They remain in the table but are excluded from score charts and band totals until delivery records exist.</p> : null}

      <FilterBar active={isFiltered || Boolean(params.get("q"))} onClear={clearFilters} description="Portfolio filters · charts and records stay in sync">
        <Field label="Project" htmlFor="portfolio-project"><Select id="portfolio-project" value={filters.project_id ?? ""} onChange={e=>update({project_id:e.target.value})}><option value="">All projects</option>{projects.map(p=><option key={p.project_id} value={p.project_id}>{p.project_name}</option>)}</Select></Field>
        <Field label="Health band" htmlFor="portfolio-health"><Select id="portfolio-health" value={filters.health_band ?? ""} onChange={e=>update({health_band:e.target.value})}><option value="">All health bands</option>{["Green","Amber","Red"].map(value=><option key={value}>{value}</option>)}</Select></Field>
        <Field label="Confidence" htmlFor="portfolio-confidence"><Select id="portfolio-confidence" value={filters.confidence_band ?? ""} onChange={e=>update({confidence_band:e.target.value})}><option value="">All confidence bands</option>{["High","Medium","Low"].map(value=><option key={value}>{value}</option>)}</Select></Field>
        <Field label="Project manager" htmlFor="portfolio-manager"><Select id="portfolio-manager" value={filters.manager ?? ""} onChange={e=>update({manager:e.target.value})}><option value="">All managers</option>{options("project_manager").map(value=><option key={value}>{value}</option>)}</Select></Field>
        <details className="sm:col-span-2 xl:col-span-4" open={Boolean(filters.domain || filters.phase || filters.priority || filters.alert_severity || filters.forecast_after || filters.forecast_before || filters.needs_attention) || undefined}>
          <summary className="cursor-pointer text-meta font-medium text-accent">More filters: attention, domain, phase, priority and forecast dates</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="Attention" htmlFor="portfolio-attention-filter"><Select id="portfolio-attention-filter" value={filters.needs_attention ?? ""} onChange={e=>update({needs_attention:e.target.value})}><option value="">Any attention position</option><option value="true">Needs attention</option><option value="false">No attention flagged</option></Select></Field>
            <Field label="Domain" htmlFor="portfolio-domain"><Select id="portfolio-domain" value={filters.domain ?? ""} onChange={e=>update({domain:e.target.value})}><option value="">All domains</option>{options("domain").map(value=><option key={value}>{value}</option>)}</Select></Field>
            <Field label="Phase" htmlFor="portfolio-phase"><Select id="portfolio-phase" value={filters.phase ?? ""} onChange={e=>update({phase:e.target.value})}><option value="">All phases</option>{options("project_phase").map(value=><option key={value}>{value}</option>)}</Select></Field>
            <Field label="Priority" htmlFor="portfolio-priority"><Select id="portfolio-priority" value={filters.priority ?? ""} onChange={e=>update({priority:e.target.value})}><option value="">All priorities</option>{options("business_priority").map(value=><option key={value}>{value}</option>)}</Select></Field>
            <Field label="Projects with alerts" htmlFor="portfolio-alerts"><Select id="portfolio-alerts" value={filters.alert_severity ?? ""} onChange={e=>update({alert_severity:e.target.value})}><option value="">Any alert position</option>{["Critical","High","Medium","Low"].map(value=><option key={value}>{value}</option>)}</Select></Field>
            <Field label="Forecast from" htmlFor="forecast-from"><TextInput id="forecast-from" type="date" value={filters.forecast_after ?? ""} onChange={e=>update({forecast_after:e.target.value})} /></Field>
            <Field label="Forecast through" htmlFor="forecast-through"><TextInput id="forecast-through" type="date" value={filters.forecast_before ?? ""} onChange={e=>update({forecast_before:e.target.value})} /></Field>
          </div>
        </details>
      </FilterBar>

      {portfolio.isError ? <ErrorState error={portfolio.error} onRetry={() => void portfolio.refetch()} /> : portfolio.isLoading || !data ? (
        <>
          <LoadingRegion label="Loading portfolio" />
          <SkeletonCards />
        </>
      ) : data.project_count === 0 ? <EmptyState headingLevel={2} title="No projects match this view" description="No records have been changed. Broaden the filters to see more of your portfolio." action={<Button onClick={clearFilters}>Clear filters</Button>} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <MetricCard
              label="Red band"
              value={data.health_bands.red}
              unit="projects"
              tone="critical"
              onClick={() => toggle("health_band", "Red")}
              active={filters.health_band === "Red"}
              caption="Projects whose calculated health is red"
            />
            <MetricCard
              label="Amber band"
              value={data.health_bands.amber}
              unit="projects"
              tone="warn"
              onClick={() => toggle("health_band", "Amber")}
              active={filters.health_band === "Amber"}
              caption="Projects to watch"
            />
            <MetricCard
              label="Low confidence"
              value={data.confidence_bands.low}
              unit="projects"
              onClick={() => toggle("confidence_band", "Low")}
              active={filters.confidence_band === "Low"}
              caption="Reporting quality limits the read on these"
            />
            <MetricCard
              label="Open alerts"
              onClick={() => document.getElementById("portfolio-attention")?.scrollIntoView({ block: "start" })}
              value={
                data.alert_severities.critical +
                data.alert_severities.high +
                data.alert_severities.medium +
                data.alert_severities.low
              }
              caption={`${data.alert_severities.critical} critical · ${data.alert_severities.high} high`}
            />
          </div>

          <div className="mt-section grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-4">
            <Card>
              <CardHeader title="Health bands" description="Distribution across the portfolio" />
              <CardBody>
                <BandDonut
                  label="Portfolio health distribution"
                  onSelect={name => toggle("health_band", name)}
                  selected={filters.health_band}
                  total={data.project_count - (data.unassessed_count ?? 0)}
                  caption="assessed"
                  data={[
                    { name: "Green", value: data.health_bands.green, colour: BAND_COLOURS["Green"]! },
                    { name: "Amber", value: data.health_bands.amber, colour: BAND_COLOURS["Amber"]! },
                    { name: "Red", value: data.health_bands.red, colour: BAND_COLOURS["Red"]! },
                  ]}
                />
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Confidence bands"
                description="How reliable the underlying records are"
              />
              <CardBody>
                <BandDonut
                  label="Portfolio confidence distribution"
                  onSelect={name => toggle("confidence_band", name)}
                  selected={filters.confidence_band}
                  total={data.project_count - (data.unassessed_count ?? 0)}
                  caption="assessed"
                  data={[
                    {
                      name: "High",
                      value: data.confidence_bands.high,
                      colour: CONFIDENCE_COLOURS["High"]!,
                    },
                    {
                      name: "Medium",
                      value: data.confidence_bands.medium,
                      colour: CONFIDENCE_COLOURS["Medium"]!,
                    },
                    {
                      name: "Low",
                      value: data.confidence_bands.low,
                      colour: CONFIDENCE_COLOURS["Low"]!,
                    },
                  ]}
                />
              </CardBody>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader
                title="Health against reporting confidence"
                description="Bubble size shows open alerts. Select a project to open it."
              />
              <CardBody>
                <HealthConfidenceScatter projects={data.projects} onSelect={id => toggle("project_id", id)} />
                <p className="mt-2 text-meta text-ink-secondary">
                  Read delivery concerns and reporting gaps together. Low data confidence does not
                  mean a recorded delivery problem can be ignored.
                </p>
              </CardBody>
            </Card>
          </div>

          <div className="mt-10 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="Alerts by severity" description="Open alerts from the rules engine" />
              <CardBody>
                <DistributionBars
                  unit="alerts"
                  onSelect={name=>toggle("alert_severity",name)}
                  preserveOrder
                  data={[
                    {
                      name: "Critical",
                      value: data.alert_severities.critical,
                      colour: "var(--critical)",
                    },
                    { name: "High", value: data.alert_severities.high, colour: "var(--advisory)" },
                    {
                      name: "Medium",
                      value: data.alert_severities.medium,
                      colour: "var(--domain-schedule)",
                    },
                    { name: "Low", value: data.alert_severities.low, colour: "var(--ok)" },
                  ]}
                />
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Projects by phase" description="Stored project lifecycle phase" />
              <CardBody>
                <DistributionBars
                  unit="projects"
                  onSelect={name=>toggle("phase",name)}
                  data={Object.entries(data.project_phases ?? {}).map(([name, value]) => ({
                    name,
                    value,
                  }))}
                />
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Projects by domain" description="Recorded portfolio composition" />
              <CardBody>
                <DistributionBars
                  unit="projects"
                  onSelect={name=>toggle("domain",name)}
                  data={Object.entries(data.project_domains ?? {}).map(([name, value]) => ({
                    name,
                    value,
                  }))}
                />
              </CardBody>
            </Card>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Projects ranked by health" description="Weakest first" />
              <CardBody>
                <ProjectHealthBars projects={data.projects} onSelect={id=>toggle("project_id",id)} />
              </CardBody>
            </Card>

            <Card id="portfolio-attention">
              <CardHeader title="Highest severity alerts" description="Engine-ranked alerts in the current scope" />
              <ul className="divide-y divide-line">
                {data.top_alerts.slice(0, 7).map((alert) => (
                  <li key={alert.alert_id} className="px-4 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-body font-medium text-ink">{alert.title}</p>
                        <p className="mt-0.5 text-meta text-ink-secondary">
                          <Link to={`/projects/${alert.project_id}`} className="text-accent hover:underline">
                            {alert.project_id}
                          </Link>{" "}
                          · {alert.alert_type_label}
                          {alert.source_ids.length > 0 ? (
                            <> · {alert.source_ids.join(", ")}</>
                          ) : null}
                        </p>
                      </div>
                      <StatusBadge label={alert.severity} tone={severityTone(alert.severity)} />
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="mt-4">
            <DataTable
              rows={data.projects}
              label="Portfolio projects"
              filterValue={params.get("q") ?? ""}
              onFilterChange={q=>update({q})}
              columns={COLUMNS}
              rowKey={(row) => row.project_id}
              searchPlaceholder="Filter projects"
              initialSortKey="health"
              emptyTitle="No projects"
              emptyDescription="The dataset contains no projects to analyse."
            />
          </div>
          <div className="mt-5"><MethodologyPopover>
            <p>Every chart and score uses the same filtered API response. Selections change the view, not the records or the calculation rules.</p>
            <p>Health and confidence are separate project indices. No portfolio average score or predicted trend is invented.</p>
          </MethodologyPopover></div>
        </>
      )}
    </>
  );
}
