import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowUpRight, CalendarDays, ChartNoAxesCombined, CircleAlert, FileText, FolderPlus, Gavel, ListChecks, RotateCw, SlidersHorizontal, Sparkles } from "lucide-react";

import { homeLabelFor } from "@/components/layout/navigation";
import { MilestoneTimeline } from "@/components/charts/milestone-timeline";
import { BandDonut } from "@/components/charts/band-donut";
import { EposBriefing } from "@/components/epos-briefing";
import { TeamTaskSummary } from "@/components/tasks/team-task-summary";
import { ProgressFoldButton } from "@/components/godui/progress-fold-button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, SkeletonCards, Skeleton } from "@/components/ui/loading-skeleton";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { StatusBadge, healthTone } from "@/components/ui/status-badge";
import { AttentionList } from "@/components/ui/attention-list";
import { BAND_COLOURS, CONFIDENCE_COLOURS } from "@/lib/chart-theme";
import { useAuth } from "@/lib/auth";
import { daysUntil, formatDate, formatScore } from "@/lib/format";
import { useActionRegister, useActivity, useAlerts, useDecisions, useMilestones, usePortfolio, useTaskRegister } from "@/lib/queries";
import { isTaskClosed } from "@/lib/task-state";
import type { ProjectSummary } from "@/types/api";

const CLOSED_ACTION_STATUSES = ["complete", "closed", "cancelled"];

/** The project a delivery role should look at first: worst health, then most critical alerts. */
function focusProject(projects: ProjectSummary[]): ProjectSummary | undefined {
  return projects
    .filter(project => project.assessment?.is_assessed !== false)
    .slice()
    .sort(
      (left, right) =>
        left.health_score - right.health_score ||
        right.critical_alert_count - left.critical_alert_count,
    )[0];
}

/** Assessed projects the API flags for attention, weakest health first. */
function attentionProjects(projects: ProjectSummary[]): ProjectSummary[] {
  return projects
    .filter(project => project.assessment?.is_assessed !== false && project.needs_attention === true)
    .sort(
      (left, right) =>
        left.health_score - right.health_score ||
        right.critical_alert_count - left.critical_alert_count,
    );
}

/** A contributor's own open work, so the first screen answers "what do I need to do?". */
function YourWork({ asOf }: { asOf?: string }): JSX.Element {
  const { user } = useAuth();
  const tasks = useTaskRegister();
  const actions = useActionRegister();
  const mine = (tasks.data ?? []).filter(task => task.owner_user_id === user?.id && !isTaskClosed(task));
  const blocked = mine.filter(task => task.is_blocked || task.status === "Blocked");
  const late = asOf ? mine.filter(task => (daysUntil(task.forecast_end_date, asOf) ?? 0) < 0) : [];
  const myActions = (actions.data ?? []).filter(action => action.owner_user_id === user?.id && !CLOSED_ACTION_STATUSES.includes(action.status.toLowerCase()));
  return (
    <Card>
      <CardHeader title="Your work" icon={ListChecks} description="Open tasks and actions assigned to your account"
        action={<Link to="/my-work" className="text-meta font-medium text-accent hover:underline">Open My work</Link>} />
      {tasks.isError ? <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} /> : (
        <CardBody className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard size="compact" label="Open tasks" value={tasks.data ? mine.length : "—"} href="/my-work" />
          <MetricCard size="compact" label="Blocked" value={tasks.data ? blocked.length : "—"} tone={blocked.length ? "critical" : "neutral"} href="/my-work?view=blocked" />
          <MetricCard size="compact" label="Past forecast" value={tasks.data ? late.length : "—"} tone={late.length ? "warn" : "neutral"} href="/my-work?view=overdue" />
          <MetricCard size="compact" label="Open actions" value={actions.data ? myActions.length : "—"} href="/my-work" />
        </CardBody>
      )}
    </Card>
  );
}

export function HomePage(): JSX.Element {
  const queryClient = useQueryClient();
  const { user, can } = useAuth();
  const portfolio = usePortfolio();
  const activity = useActivity(undefined, 8);
  const decisions = useDecisions();
  const alerts = useAlerts();
  const focus = portfolio.data ? focusProject(portfolio.data.projects) : undefined;
  const milestones = useMilestones(focus?.project_id ?? "");

  const firstName = user?.full_name.split(" ")[0] ?? "there";
  // Only a refresh the reader asked for is announced; background refetches stay quiet.
  const [refreshing, setRefreshing] = useState(false);
  async function refresh(): Promise<void> {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({ predicate: query => ["portfolio", "task-register", "activity", "alerts", "decisions"].includes(String(query.queryKey[0])) });
    } finally {
      setRefreshing(false);
    }
  }

  if (portfolio.isError) {
    return (
      <Card>
        <ErrorState error={portfolio.error} onRetry={() => void portfolio.refetch()} />
      </Card>
    );
  }

  const data = portfolio.data;
  const emptyWorkspace = data !== undefined && data.project_count === 0;
  const atRisk = data ? attentionProjects(data.projects) : [];
  const pendingDecisions =
    decisions.data?.filter((decision) => decision.status.toLowerCase() === "proposed") ?? [];
  const teamWork = can("work.manage") ? <div className="mt-5"><TeamTaskSummary /></div> : null;

  return (
    <>
      <PageHeader
        title={homeLabelFor(can)}
        description={
          emptyWorkspace
            ? `${firstName}, your workspace has no projects yet.`
            : data
            ? `${firstName}, here is the current delivery position and the work requiring review.`
            : "Loading your portfolio position."
        }
        meta={user ? <StatusBadge label={user.role_label} tone="accent" /> : null}
        actions={
          <ProgressFoldButton variant="secondary" size="sm" status={refreshing ? "loading" : "idle"}
            progressLabel="Refreshing portfolio summary" onClick={() => void refresh()}>
            <RotateCw size={14} aria-hidden="true" />{refreshing ? "Refreshing" : "Refresh"}
          </ProgressFoldButton>
        }
      />

      <nav aria-label="Workspace shortcuts" className="workspace-quicklinks">
        <Link to="/my-work"><ListChecks size={15} aria-hidden="true" />My work</Link>
        <Link to="/calendar"><CalendarDays size={15} aria-hidden="true" />Calendar</Link>
        {can("scenario.run") ? <Link to="/scenarios"><SlidersHorizontal size={15} aria-hidden="true" />Explore a scenario</Link> : null}
        {can("copilot.ask") ? <Link to="/ask"><Sparkles size={15} aria-hidden="true" />Ask about your projects</Link> : null}
        {can("report.read") ? <Link to="/report"><FileText size={15} aria-hidden="true" />Executive report</Link> : null}
      </nav>

      {can("work.update") && !can("work.manage") ? <div className="mb-5"><YourWork asOf={data?.as_of_date} /></div> : null}

      {emptyWorkspace ? (
        <Card>
          <EmptyState
            headingLevel={2}
            title="No projects yet"
            description={can("project.create")
              ? "Create the first project to start tracking delivery health, risks and decisions."
              : "You have not been added to a project yet. Ask a project manager or an administrator to add you."}
            action={can("project.create") ? (
              <Link to="/projects/new" className="inline-flex items-center gap-2 rounded-control border border-line bg-surface px-4 py-2.5 font-medium text-accent hover:border-accent"><FolderPlus size={15} aria-hidden="true" />Create project</Link>
            ) : undefined}
          />
        </Card>
      ) : <>
      {portfolio.isLoading ? (
        <>
          <LoadingRegion label="Loading portfolio summary" />
          <SkeletonCards />
        </>
      ) : data ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <MetricCard
            label="Projects"
            value={data.project_count}
            unit="projects"
            href="/portfolio"
            caption={`${data.health_bands.green} green · ${data.health_bands.amber} amber · ${data.health_bands.red} red${data.unassessed_count ? ` · ${data.unassessed_count} not yet assessed` : ""}`}
          />
          <MetricCard
            label="Needing attention"
            value={atRisk.length}
            unit="projects"
            tone="critical"
            href="/portfolio?needs_attention=true"
            caption="Amber or red health, or a critical alert"
          />
          <MetricCard
            label="Critical alerts"
            value={data.alert_severities.critical}
            unit="alerts"
            tone="critical"
            href="/portfolio?alert_severity=Critical"
            caption={`Also open: ${data.alert_severities.high} high and ${data.alert_severities.medium} medium`}
          />
          <MetricCard
            label="Low reporting confidence"
            value={data.confidence_bands.low}
            unit="projects"
            href="/portfolio?confidence_band=Low"
            caption="Projects where the data itself needs work"
          />
        </div>
      ) : null}

      {data ? <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <EposBriefing data={data} isLoading={portfolio.isLoading} canAsk={can("copilot.ask")} />
        <Card><CardHeader title="Health and confidence" icon={ChartNoAxesCombined} description="Delivery position and evidence quality are separate signals" />
          <CardBody className="grid gap-4 sm:grid-cols-2">
            <div><h3 className="text-center text-meta font-medium">Health</h3><BandDonut total={data.project_count - (data.unassessed_count ?? 0)} caption="assessed" label="Executive health distribution" data={[
              {name:"Green",value:data.health_bands.green,colour:BAND_COLOURS.Green!},
              {name:"Amber",value:data.health_bands.amber,colour:BAND_COLOURS.Amber!},
              {name:"Red",value:data.health_bands.red,colour:BAND_COLOURS.Red!},
            ]} /></div>
            <div><h3 className="text-center text-meta font-medium">Confidence</h3><BandDonut total={data.project_count - (data.unassessed_count ?? 0)} caption="assessed" label="Executive confidence distribution" data={[
              {name:"High",value:data.confidence_bands.high,colour:CONFIDENCE_COLOURS.High!},
              {name:"Medium",value:data.confidence_bands.medium,colour:CONFIDENCE_COLOURS.Medium!},
              {name:"Low",value:data.confidence_bands.low,colour:CONFIDENCE_COLOURS.Low!},
            ]} /></div>
          </CardBody>
        </Card>
      </div> : null}

      {teamWork}

      <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader
              title="Needs your attention"
              icon={CircleAlert}
              description="Amber or red health, or a critical alert · weakest health first"
              action={
                <Link to={atRisk.length > 5 ? "/portfolio?needs_attention=true" : "/portfolio"} className="text-meta font-medium text-accent hover:underline">
                  {atRisk.length > 5 ? `All ${atRisk.length}` : "Full portfolio"}
                </Link>
              }
            />
            {portfolio.isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : atRisk.length === 0 ? (
              <EmptyState
                title="Nothing needs attention"
                description="No assessed project has amber or red health or a critical alert. Projects not yet assessed are listed in the portfolio."
                action={
                  <Link to="/portfolio" className="inline-flex items-center gap-2 rounded-control border border-line bg-surface px-4 py-2.5 font-medium text-accent hover:border-accent">Open portfolio <ArrowUpRight size={15} aria-hidden="true" /></Link>
                }
              />
            ) : (
              <ul className="divide-y divide-line">
                {atRisk.slice(0, 5).map((project) => (
                  <li key={project.project_id}>
                    <Link
                      to={`/projects/${project.project_id}`}
                      className="workspace-attention-link"
                    >
                      <div className="min-w-0">
                        <p className="break-words text-body font-medium text-ink">{project.project_name}</p>
                        <p className="mt-0.5 text-meta text-ink-secondary">
                          {project.project_id} · {project.project_manager} · forecast{" "}
                          {formatDate(project.forecast_end_date)}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="text-meta text-ink-secondary" data-numeric>
                          {project.open_alert_count} open
                        </span>
                        <span className="text-body font-semibold text-ink" data-numeric>
                          {formatScore(project.health_score)}
                        </span>
                        <StatusBadge
                          label={project.health_band}
                          tone={healthTone(project.health_band)}
                        />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {focus && milestones.data && milestones.data.length > 0 ? (
            <Card>
              <CardHeader
                title="Milestone slip"
                icon={CalendarDays}
                description={`${focus.project_name} — baseline against forecast`}
                action={
                  <Link
                    to={`/projects/${focus.project_id}`}
                    className="text-meta font-medium text-accent hover:underline"
                  >
                    Open project
                  </Link>
                }
              />
              <CardBody>
                <MilestoneTimeline
                  milestones={milestones.data}
                  asOfDate={data?.as_of_date ?? focus.forecast_end_date ?? ""}
                />
              </CardBody>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Decisions waiting"
              icon={Gavel}
              description="Proposed and not yet resolved"
              action={
                <Link to="/decisions" className="text-meta font-medium text-accent hover:underline">
                  All decisions
                </Link>
              }
            />
            {decisions.isError ? <ErrorState error={decisions.error} onRetry={() => void decisions.refetch()} /> : decisions.isLoading ? <div className="p-4"><Skeleton className="h-24 w-full" /></div> : pendingDecisions.length === 0 ? (
              <EmptyState
                title="No decision is waiting"
                description="No proposed decisions are present in the current scope."
                className="py-8"
              />
            ) : (
              <ul className="divide-y divide-line">
                {pendingDecisions.slice(0, 5).map((decision) => (
                  <li key={decision.decision_id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <Link
                        to={`/projects/${decision.project_id}?tab=decisions`}
                        className="text-meta font-medium text-accent hover:underline"
                      >
                        {decision.project_id}
                      </Link>
                      <StatusBadge label={decision.status} tone="warn" />
                    </div>
                    <p className="mt-1 text-body font-medium text-ink">{decision.title}</p>
                    <p className="mt-0.5 text-meta text-ink-secondary">
                      {decision.owner} · {formatDate(decision.decision_date)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="Priority attention" icon={CircleAlert} description="Risks, blockers, actions and schedule warnings, most severe first" />
            {alerts.isError ? <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} /> : alerts.isLoading ? <div className="p-4"><Skeleton className="h-40 w-full" /></div> : !alerts.data?.length ? (
              <EmptyState
                title="No open alerts"
                description="The current analysis reports no alerts."
                className="py-8"
              />
            ) : (
              <CardBody><AttentionList alerts={alerts.data} projects={data?.projects ?? []} limit={5} /></CardBody>
            )}
          </Card>

          <Card>
            <CardHeader title="Recent activity" icon={Activity} description="Changes recorded in EPOS" />
            {activity.isError ? <ErrorState error={activity.error} onRetry={() => void activity.refetch()} /> : activity.isLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : !activity.data || activity.data.length === 0 ? (
              <EmptyState
                title="No activity yet"
                description="Edits made in EPOS appear here with the person who made them."
                className="py-8"
              />
            ) : (
              <ul className="divide-y divide-line">
                {activity.data.map((event) => (
                  <li key={event.id} className="px-4 py-2.5">
                    <p className="text-body text-ink">{event.headline}</p>
                    <p className="mt-0.5 text-meta text-ink-secondary">
                      {event.actor_name ?? "System"} · {formatDate(event.occurred_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
      </>}
    </>
  );
}
