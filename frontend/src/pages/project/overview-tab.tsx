import { useState } from "react";
import { Link } from "react-router-dom";
import { Activity, CircleAlert, Gauge, Milestone, TriangleAlert } from "lucide-react";

import { MilestoneTimeline } from "@/components/charts/milestone-timeline";
import { DataQualityPanel } from "@/components/data-quality-panel";
import { GatePosition } from "@/components/gate-position";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Drawer } from "@/components/ui/drawer";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SkeletonTable } from "@/components/ui/loading-skeleton";
import { ScoreCard } from "@/components/ui/score-card";
import { Section, StatTile } from "@/components/ui/section";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, confidenceTone, healthTone, severityTone } from "@/components/ui/status-badge";
import { useAuth } from "@/lib/auth";
import { formatDate, formatPercent, formatScore } from "@/lib/format";
import { useActions, useGates, useMilestones, useRecordStatusUpdate, useTasks, useTraceability } from "@/lib/queries";
import { WhatChanged } from "@/pages/project/what-changed";
import type { Alert, ProjectDashboard } from "@/types/api";

/** A project with no delivery records cannot be scored; showing zero would read as failure. */
function GettingStarted({ projectId }: { projectId: string }): JSX.Element {
  const steps = [
    { label: "Confirm the delivery team", detail: "Record who owns the work." },
    { label: "Add milestones", detail: "Milestones establish the schedule baseline." },
    { label: "Add work items", detail: "Tasks show progress against the plan." },
    { label: "Identify risks", detail: "A register with owners strengthens reporting confidence." },
  ];

  return (
    <Card>
      <CardHeader title="Getting started" description="Add delivery information to generate an overview" />
      <CardBody>
        <ol className="space-y-3">
          {steps.map((step, index) => (
            <li key={step.label} className="flex gap-3">
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-subtle text-[11px] font-semibold text-ink-secondary"
              >
                {index + 1}
              </span>
              <div>
                <p className="text-body font-medium text-ink">{step.label}</p>
                <p className="text-meta text-ink-secondary">{step.detail}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-4 border-t border-line pt-3 text-meta text-ink-muted">
          Delivery status for {projectId} is not yet assessed.
        </p>
      </CardBody>
    </Card>
  );
}

function AlertList({ alerts }: { alerts: Alert[] }): JSX.Element {
  return (
    <ul className="divide-y divide-line">
      {alerts.map((alert) => (
        <li key={alert.alert_id} className="px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-body font-medium text-ink">{alert.title}</p>
              <p className="mt-0.5 text-meta text-ink-muted">{alert.alert_type_label}</p>
            </div>
            <StatusBadge label={alert.severity} tone={severityTone(alert.severity)} />
          </div>
          <p className="mt-1.5 text-body text-ink-secondary">{alert.explanation}</p>
          <p className="mt-1.5 text-body text-ink">
            <span className="font-medium">Next step: </span>
            {alert.recommended_next_step}
          </p>
          <SourceList ids={alert.source_ids} className="mt-2" />
        </li>
      ))}
    </ul>
  );
}

/** Record that the project's status was reviewed today. The server dates it, never the browser. */
export function StatusUpdateAction({ projectId }: { projectId: string }): JSX.Element | null {
  const { can } = useAuth();
  const record = useRecordStatusUpdate(projectId);
  if (!can("project.update")) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" disabled={record.isPending} onClick={() => record.mutate()}>
        {record.isPending ? "Recording" : "Record status update"}
      </Button>
      {record.isError ? <p role="alert" className="text-meta text-critical">{record.error.message}</p> : null}
    </div>
  );
}

export function OverviewTab({ dashboard }: { dashboard: ProjectDashboard }): JSX.Element {
  const { project, health, confidence, alerts } = dashboard;
  const milestones = useMilestones(project.project_id);
  const tasks = useTasks(project.project_id);
  const traceability = useTraceability(project.project_id);
  const actions = useActions(project.project_id);
  const gates = useGates(project.project_id);
  const [openAlerts, setOpenAlerts] = useState(false);
  const [openQuality, setOpenQuality] = useState(false);
  const projectPath=`/projects/${project.project_id}`;
  const showWorking = () => {
    const detail=document.getElementById("project-working") as HTMLDetailsElement | null;
    if(detail) { detail.open=true; detail.querySelector("summary")?.focus(); }
  };

  const notYetAssessed = dashboard.assessment ? !dashboard.assessment.is_assessed : health.factors.length === 0 || health.source_ids.length <= 1;
  if (notYetAssessed) {
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <GettingStarted projectId={project.project_id} />
        </div>
      </div>
    );
  }

  const asOf = health.as_of_date;
  const allMilestones = milestones.data ?? [];
  const allTasks = tasks.data ?? [];

  const openMilestones = allMilestones
    .filter((m) => m.forecast_date && !m.actual_date && !["complete","completed"].includes(m.status.toLowerCase()))
    .sort((a, b) => (a.forecast_date ?? "").localeCompare(b.forecast_date ?? ""));

  // An outstanding milestone whose date has passed is overdue, not "next".
  const upcoming = openMilestones.find((m) => (m.forecast_date ?? "") >= asOf);
  const nextMilestone = upcoming ?? openMilestones[0];
  const milestoneIsOverdue = Boolean(nextMilestone && !upcoming);

  const lateMilestones = allMilestones.filter((m) => (m.forecast_variance_days ?? 0) > 0 && !m.actual_date);
  const blockedTasks = allTasks.filter((t) => t.is_blocked);
  const riskFactor = health.factors.find(factor=>factor.label==="Risk Management");

  const critical = alerts.filter((a) => a.severity === "Critical");
  const unownedDrivers = health.critical_drivers.filter((d) =>
    d.message.toLowerCase().includes("no mitigation owner"),
  );

  // Short, countable statements. The detail lives one click away.
  const attention: string[] = [];
  if (lateMilestones.length > 0) {
    attention.push(
      `${lateMilestones.length} ${lateMilestones.length === 1 ? "milestone is" : "milestones are"} forecast beyond baseline.`,
    );
  }
  if (blockedTasks.length > 0) {
    attention.push(
      `${blockedTasks.length} ${blockedTasks.length === 1 ? "blocker affects" : "blockers affect"} delivery.`,
    );
  }
  if (unownedDrivers.length > 0) {
    attention.push(
      `${unownedDrivers.length} ${unownedDrivers.length === 1 ? "risk has" : "risks have"} no mitigation owner.`,
    );
  }
  if (confidence.data_quality_issues.length > 0) {
    attention.push(
      `${confidence.data_quality_issues.length} reporting ${confidence.data_quality_issues.length === 1 ? "gap weakens" : "gaps weaken"} the delivery read.`,
    );
  }

  return (
    <>
      <Section title="Delivery position" description={`Calculated as at ${asOf}`} icon={Gauge}>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <StatTile
            label="Health"
            value={formatScore(health.score)}
            tone={health.band === "Red" ? "critical" : health.band === "Amber" ? "warn" : "ok"}
            caption={health.band}
            onClick={showWorking}
          />
          <StatTile
            label="Confidence"
            value={formatScore(confidence.score)}
            tone={confidence.band === "Low" ? "critical" : confidence.band === "Medium" ? "warn" : "ok"}
            caption={confidence.band}
            onClick={()=>setOpenQuality(true)}
          />
          <StatTile label="Risk Management" value={riskFactor ? formatScore(riskFactor.score) : "—"} caption="Recorded health factor / 100" href={`${projectPath}?tab=risks`} />
          <StatTile
            label={milestoneIsOverdue ? "Overdue milestone" : "Next milestone"}
            value={<span className="text-card">{nextMilestone ? formatDate(nextMilestone.forecast_date) : "—"}</span>}
            tone={milestoneIsOverdue ? "critical" : "neutral"}
            caption={milestones.isLoading ? "Loading" : nextMilestone ? nextMilestone.milestone_name : "None scheduled"}
            href={`${projectPath}?tab=work`}
          />
          <StatTile
            label="Open alerts"
            value={alerts.length}
            tone={critical.length > 0 ? "critical" : "neutral"}
            caption={`${critical.length} critical`}
            onClick={()=>setOpenAlerts(true)}
          />
          <StatTile
            label="Blocked work"
            value={tasks.data ? blockedTasks.length : "—"}
            tone={blockedTasks.length > 0 ? "warn" : "neutral"}
            caption={!tasks.data ? "Loading" : blockedTasks.length > 0 ? "Needs unblocking" : "Nothing blocked"}
            href={`${projectPath}?tab=work&state=blocked`}
          />
          <StatTile label="Requirements and testing" value={traceability.data?.total_requirements ?? "—"} caption={traceability.data ? `${formatPercent(traceability.data.coverage_percent)} verified coverage` : traceability.isLoading ? "Loading" : "Verification data unavailable"} href={`${projectPath}?tab=requirements`} />
          <StatTile label="Actions" value={actions.data?.length ?? "—"} caption={actions.isLoading ? "Loading" : "Recorded follow-through items"} href={`${projectPath}?tab=team`} />
        </div>
      </Section>

      {attention.length > 0 ? (
        <Section
          title="Needs attention"
          description="The short version. Open the detail when you are ready to act."
          icon={TriangleAlert}
          accent="warn"
          actions={
            <Button size="sm" onClick={() => setOpenAlerts(true)}>
              <CircleAlert aria-hidden="true" className="h-3.5 w-3.5" />
              Review {alerts.length} {alerts.length === 1 ? "alert" : "alerts"}
            </Button>
          }
        >
          <Card>
            <CardBody>
              <ul className="space-y-2">
                {attention.map((line) => (
                  <li key={line} className="flex gap-2.5 text-body text-ink">
                    <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
                    {line}
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap gap-2"><Link to={`${projectPath}?tab=work`}><Button size="sm">Review delivery plan</Button></Link><Button size="sm" onClick={()=>setOpenQuality(true)}>Open correction list</Button></div>
              <SourceList ids={[...lateMilestones.map(m=>m.milestone_id),...blockedTasks.map(t=>t.task_id),...unownedDrivers.flatMap(driver=>driver.source_ids)]} className="mt-3" label="Supporting records" />
            </CardBody>
          </Card>
        </Section>
      ) : null}

      <WhatChanged projectId={project.project_id} />

      <Section title="Gate readiness" description="Mandatory blockers remain visible before any completion percentage" icon={Gauge}>
        {gates.isError ? <ErrorState error={gates.error} onRetry={()=>void gates.refetch()}/> : gates.isLoading ? <SkeletonTable rows={2}/> : gates.data?.length ? <div className="grid gap-3 xl:grid-cols-2">{gates.data.map(gate=><GatePosition gate={gate} key={gate.gate_id}/>)}</div> : <p className="text-body text-ink-secondary">No gates are configured for this project. <Link to={`${projectPath}?tab=gates`} className="text-accent hover:underline">Open readiness records</Link></p>}
      </Section>

      <Section title="Schedule" description="Baseline against forecast" icon={Milestone} accent="indigo">
        {milestones.isError ? <ErrorState error={milestones.error} onRetry={()=>void milestones.refetch()}/> : milestones.isLoading ? <SkeletonTable rows={3}/> : allMilestones.length === 0 ? (
          <Card>
            <EmptyState
              title="No milestones recorded"
              description="Milestones establish the schedule baseline that delivery is measured against."
              className="py-8"
            />
          </Card>
        ) : (
          <Card>
            <CardBody>
              <MilestoneTimeline milestones={allMilestones} asOfDate={asOf} />
            </CardBody>
          </Card>
        )}
      </Section>

      <details id="project-working" className="disclosure mt-8">
      <summary>Score working, methodology and project record</summary>
      <div className="p-4"><Section
        title="Analysis detail"
        description="How each score was calculated, and from which records"
        icon={Activity}
        accent="purple"
      >
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ScoreCard
            title="Project health"
            score={health.score}
            band={health.band}
            tone={healthTone(health.band)}
            factors={health.factors}
            drivers={health.critical_drivers}
            sourceIds={health.source_ids}
            limitations={health.assumptions_or_limitations}
            asOfDate={health.as_of_date}
          />
          <ScoreCard
            title="Reporting confidence"
            score={confidence.score}
            band={confidence.band}
            tone={confidenceTone(confidence.band)}
            factors={confidence.factors}
            sourceIds={confidence.source_ids}
            limitations={confidence.assumptions_or_limitations}
            asOfDate={confidence.as_of_date}
          />
        </div>

        <Card className="mt-4">
          <CardHeader
            title="Project record"
            description="Stored values, shown without interpretation"
            action={<StatusUpdateAction projectId={project.project_id} />}
          />
          <CardBody>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-3">
              {[
                ["Project manager", project.project_manager],
                ["Domain", project.domain],
                ["Phase", project.project_phase],
                ["Business priority", project.business_priority],
                ["Start", formatDate(project.start_date)],
                ["Baseline end", formatDate(project.baseline_end_date)],
                ["Forecast end", formatDate(project.forecast_end_date)],
                ["Last status update", formatDate(project.status_update_date)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-meta text-ink-muted">{label}</dt>
                  <dd className="mt-0.5 text-body text-ink">{value}</dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
      </Section>
      </div></details>

      <Drawer open={openQuality} onClose={()=>setOpenQuality(false)} title="Data quality scorecard" description={project.project_name} width="max-w-3xl"><DataQualityPanel confidence={confidence}/></Drawer>

      <Drawer
        open={openAlerts}
        onClose={() => setOpenAlerts(false)}
        title="Needs attention"
        description={`${alerts.length} raised for ${project.project_name}`}
        width="max-w-2xl"
        footer={
          <Link to={`/projects/${project.project_id}?tab=risks`}>
            <Button variant="primary">Open risk register</Button>
          </Link>
        }
      >
        {alerts.length === 0 ? (
          <EmptyState
            title="No open alerts"
            description="Nothing in this project currently crosses an alert threshold."
          />
        ) : (
          <div className="card overflow-hidden">
            <AlertList alerts={alerts} />
          </div>
        )}

        {confidence.data_quality_issues.length > 0 ? (
          <Card className="mt-4">
            <CardHeader title="Reporting gaps" description="Fix these to make the score more dependable" />
            <ul className="divide-y divide-line">
              {confidence.data_quality_issues.map((issue) => (
                <li key={`${issue.issue_type}-${issue.message}`} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-body text-ink">{issue.message}</p>
                    <StatusBadge label={issue.severity} tone={severityTone(issue.severity)} />
                  </div>
                  <p className="mt-1 text-meta text-ink-secondary">{issue.remediation_hint}</p>
                  <SourceList ids={issue.source_ids} className="mt-1.5" />
                </li>
              ))}
            </ul>
          </Card>
        ) : null}
      </Drawer>
    </>
  );
}
