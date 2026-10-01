import { Link, useParams, useSearchParams } from "react-router-dom";

import { OverviewTab } from "@/pages/project/overview-tab";
import { WorkTab } from "@/pages/project/work-tab";
import { GatesTab } from "@/pages/project/gates-tab";
import { RisksTab } from "@/pages/project/risks-tab";
import { IssuesTab } from "@/pages/project/issues-tab";
import { AssumptionsTab } from "@/pages/project/assumptions-tab";
import { RequirementsTab } from "@/pages/project/requirements-tab";
import { ChangesTab } from "@/pages/project/changes-tab";
import { DecisionsTab } from "@/pages/project/decisions-tab";
import { MeetingsTab } from "@/pages/project/meetings-tab";
import { TeamTab } from "@/pages/project/team-tab";
import { MembersTab } from "@/pages/project/members-tab";
import { ActivityTab } from "@/pages/project/activity-tab";
import { MagicTab } from "@/components/godui/magic-tab";
import { TeamTaskSummary } from "@/components/tasks/team-task-summary";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, Skeleton } from "@/components/ui/loading-skeleton";
import { PageHeader } from "@/components/ui/page-header";
import { Field, Select } from "@/components/ui/form";
import { StatusBadge, confidenceTone, healthTone } from "@/components/ui/status-badge";
import { TermHelp } from "@/components/ui/term-help";
import { cn } from "@/lib/cn";
import { formatDate, formatScore } from "@/lib/format";
import { useProjectDashboard } from "@/lib/queries";
import { useAuth } from "@/lib/auth";

const TAB_GROUPS = ["Overview", "Delivery", "Controls", "Evidence"] as const;

const TABS = [
  { id: "overview", label: "Overview", group: "Overview" },
  { id: "work", label: "Delivery plan", group: "Delivery" },
  { id: "members", label: "Team members", group: "Delivery" },
  { id: "team", label: "Capacity & actions", group: "Delivery" },
  { id: "risks", label: "Risks", group: "Controls" },
  { id: "issues", label: "Issues", group: "Controls" },
  { id: "assumptions", label: "Assumptions", group: "Controls" },
  { id: "changes", label: "Change requests", group: "Controls" },
  { id: "decisions", label: "Decisions", group: "Controls" },
  { id: "meetings", label: "Meetings", group: "Controls" },
  { id: "requirements", label: "Requirements", group: "Evidence" },
  { id: "gates", label: "Gates", group: "Evidence" },
  { id: "activity", label: "Audit trail", group: "Evidence" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function ProjectWorkspacePage(): JSX.Element {
  const { can } = useAuth();
  const tabs = TABS.filter(tab => tab.id !== "members" || can("project_members.manage"));
  const { projectId = "" } = useParams<{ projectId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const dashboard = useProjectDashboard(projectId);

  const requested = searchParams.get("tab") as TabId | null;
  const active: TabId = tabs.some((tab) => tab.id === requested) && requested ? requested : "overview";
  const activeGroup = tabs.find(tab => tab.id === active)?.group ?? "Overview";
  const visibleTabs = tabs.filter(tab => tab.group === activeGroup);
  const sectionHelp = active === "gates" ? "gateReadiness" : active === "requirements" ? "traceState" : active === "assumptions" ? "assumption" : undefined;

  function selectTab(tab: TabId): void {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
  }

  if (dashboard.isError) {
    return (
      <Card>
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
        <div className="pb-6 text-center">
          <Link to="/projects" className="text-meta font-medium text-accent hover:underline">
            Back to projects
          </Link>
        </div>
      </Card>
    );
  }

  if (dashboard.isLoading || !dashboard.data) {
    return (
      <>
        <LoadingRegion label="Loading project" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="mt-3 h-5 w-96" />
        <Skeleton className="mt-6 h-64 w-full" />
      </>
    );
  }

  const { project, health, confidence, assessment } = dashboard.data;
  const isAssessed = assessment?.is_assessed !== false;

  return (
    <>
      <PageHeader
        title={project.project_name}
        scope="Project workspace"
        asOfDate={health.as_of_date}
        description={`${project.project_id} · ${project.domain} · ${project.project_phase}`}
        meta={
          <>
            {isAssessed ? <>
              <div className="flex flex-wrap items-center gap-1">
                <StatusBadge label={`Health ${formatScore(health.score)}`} tone={healthTone(health.band)} />
                <TermHelp term="health" />
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <StatusBadge label={`Confidence ${formatScore(confidence.score)}`} tone={confidenceTone(confidence.band)} />
                <TermHelp term="confidence" />
              </div>
            </> : <>
              <StatusBadge label="Not yet assessed" tone="neutral" />
              <span className="text-meta text-ink-secondary">{assessment?.reason || "An assessment is not available for this project yet."}</span>
            </>}
            <span className="text-meta text-ink-secondary">
              Managed by {project.project_manager} · forecast end {formatDate(project.forecast_end_date)}
            </span>
          </>
        }
      />

      <div className="mb-5" data-print-hide>
        <div className="mb-3 sm:hidden">
          <Field label="Project section" htmlFor="project-section">
            <Select id="project-section" value={active} onChange={event => selectTab(event.target.value as TabId)}>
              {TAB_GROUPS.map(group => <optgroup key={group} label={group}>
                {tabs.filter(tab => tab.group === group).map(tab => <option key={tab.id} value={tab.id}>{tab.label}</option>)}
              </optgroup>)}
            </Select>
          </Field>
        </div>
        <div role="group" aria-label="Project categories" className="mb-3 hidden flex-wrap gap-2 sm:flex">
          {TAB_GROUPS.map(group => <button key={group} type="button" aria-pressed={activeGroup === group}
            aria-controls="project-section-tabs"
            className={cn("min-h-10 rounded-control border px-3 py-2 text-meta font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
              activeGroup === group ? "border-accent bg-accent-tint text-accent" : "border-line bg-surface text-ink-secondary hover:border-line-strong hover:text-ink")}
            onClick={() => {
              const firstTab = tabs.find(tab => tab.group === group);
              if (activeGroup !== group && firstTab) selectTab(firstTab.id);
            }}>
            {group}
          </button>)}
        </div>
        {/* A category with a single section needs no tab strip; it stays available to assistive tech. */}
        <MagicTab key={activeGroup} id="project-section-tabs" aria-label="Project sections" className={cn("workspace-project-tabs hidden flex-wrap sm:flex", visibleTabs.length === 1 && "sm:sr-only")}
          variant="secondary" size="sm" value={active} onValueChange={value => selectTab(value as TabId)}
          items={visibleTabs.map(tab => ({ value: tab.id, label: tab.label, id: `project-${tab.id}-tab`, controls: `project-${tab.id}-panel` }))} />
        {sectionHelp ? <TermHelp term={sectionHelp} className="mt-3" /> : null}
      </div>

      {active === "overview" && can("work.manage") ? <div className="mb-5"><TeamTaskSummary projectId={projectId} /></div> : null}

      {visibleTabs.map(tab => <div key={tab.id} role="tabpanel" id={`project-${tab.id}-panel`}
        aria-labelledby={`project-${tab.id}-tab`} hidden={active !== tab.id} tabIndex={0}>
      {active === tab.id ? <>
      {active === "overview" ? <OverviewTab dashboard={dashboard.data} /> : null}
      {active === "work" ? <WorkTab projectId={projectId} asOfDate={health.as_of_date} projectStart={project.start_date} /> : null}
      {active === "members" ? <MembersTab projectId={projectId} /> : null}
      {active === "gates" ? <GatesTab projectId={projectId} /> : null}
      {active === "risks" ? <RisksTab projectId={projectId} /> : null}
      {active === "issues" ? <IssuesTab projectId={projectId} /> : null}
      {active === "assumptions" ? <AssumptionsTab projectId={projectId} /> : null}
      {active === "requirements" ? <RequirementsTab projectId={projectId} /> : null}
      {active === "changes" ? <ChangesTab projectId={projectId} /> : null}
      {active === "decisions" ? <DecisionsTab projectId={projectId} /> : null}
      {active === "meetings" ? <MeetingsTab projectId={projectId} /> : null}
      {active === "team" ? <TeamTab projectId={projectId} /> : null}
      {active === "activity" ? <ActivityTab projectId={projectId} /> : null}
      </> : null}
      </div>)}
    </>
  );
}
