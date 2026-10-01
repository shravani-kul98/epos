import { useState } from "react";
import { ArrowRight, FlaskConical, MessageSquareText, ScanLine, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import {
  ScenarioFactorWaterfall,
  ScenarioResponseChart,
} from "@/components/charts/scenario-analysis";
import { ScenarioTimeline } from "@/components/charts/scenario-timeline";
import { DependencyHandoffs } from "@/components/charts/dependency-handoffs";
import { Button } from "@/components/ui/button";
import { ProgressFoldButton } from "@/components/godui/progress-fold-button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { PageHeader } from "@/components/ui/page-header";
import { MethodologyPopover } from "@/components/ui/methodology-popover";
import { LoadingRegion, SkeletonCards } from "@/components/ui/loading-skeleton";
import { SourceList } from "@/components/ui/source-list";
import { StatusBadge, confidenceTone, healthTone } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { formatDate, formatDays, formatDelta, formatScore } from "@/lib/format";
import {
  useDependencies,
  useExplainScenario,
  usePortfolio,
  useRunScenario,
  useRunScenarioSensitivity,
} from "@/lib/queries";

export function ScenariosPage(): JSX.Element {
  const dependencies = useDependencies();
  const portfolio = usePortfolio();
  const runScenario = useRunScenario();
  const runSensitivity = useRunScenarioSensitivity();
  const explainScenario = useExplainScenario();
  const [dependencyId, setDependencyId] = useState("");
  const [delayDays, setDelayDays] = useState(15);
  const [formError, setFormError] = useState<string | null>(null);
  const [dependencySearch, setDependencySearch] = useState("");

  const options = dependencies.data ?? [];
  const projectName = (projectId: string) =>
    portfolio.data?.projects?.find(project => project.project_id === projectId)?.project_name ?? projectId;
  const optionLabel = (option: (typeof options)[number]) => `${projectName(option.project_id)} · ${option.dependency_name} — ${option.dependency_id}`;
  const selectedId = dependencyId || options[0]?.dependency_id || "";
  const selected = options.find((option) => option.dependency_id === selectedId);
  const result = runScenario.data;
  const isDraftChanged = result && (result.dependency_id !== selectedId || result.additional_delay_days !== delayDays);

  function run(): void {
    setFormError(null);
    if (!selectedId) {
      setFormError("Choose a dependency to model.");
      return;
    }
    if (!Number.isInteger(delayDays) || delayDays < 1 || delayDays > 365) {
      setFormError("Enter a whole number of days between 1 and 365.");
      return;
    }
    runSensitivity.reset();
    explainScenario.reset();
    runScenario.mutate({ dependency_id: selectedId, additional_delay_days: delayDays });
    runSensitivity.mutate({ intervention_type: "dependency_delay", target_id: selectedId });
  }

  return (
    <>
      <PageHeader
        title="Scenarios"
        description="Explore a decision before changing the plan. See what moves, why it moves, and what needs review."
        scope="What-if workspace · calculated results"
        asOfDate={result?.as_of_date}
      />

      <div className="scenario-workflow" aria-label="Scenario workflow">
        <span><FlaskConical size={17} aria-hidden="true" /> Set the change</span><ArrowRight size={14} aria-hidden="true" />
        <span><ScanLine size={17} aria-hidden="true" /> Compare the evidence</span><ArrowRight size={14} aria-hidden="true" />
        <span><MessageSquareText size={17} aria-hidden="true" /> Review the decision</span>
        <span className="scenario-workflow-note">A simulation, never a change to your records</span>
      </div>
      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(280px,340px)_minmax(0,1fr)]">
        <Card className="scenario-input-card h-fit">
          <CardHeader title="Model a delay" description="Choose a dependency and the additional slip" />
          <CardBody className="space-y-4">
            {dependencies.isError ? (
              <ErrorState error={dependencies.error} onRetry={() => void dependencies.refetch()} />
            ) : (
              <>
                {options.length>8 ? <Field label="Find a dependency" htmlFor="dependency-search"><TextInput id="dependency-search" type="search" value={dependencySearch} onChange={e=>setDependencySearch(e.target.value)} placeholder="Name or reference"/></Field> : null}
                <Field label="Dependency" htmlFor="dependency">
                  <Select
                    id="dependency"
                    value={selectedId}
                    onChange={(event) => {
                      setDependencyId(event.target.value);
                      setFormError(null);
                      runScenario.reset();
                      runSensitivity.reset();
                      explainScenario.reset();
                    }}
                    disabled={dependencies.isLoading || runScenario.isPending || runSensitivity.isPending}
                  >
                    {options.filter(option=>option.dependency_id===selectedId||optionLabel(option).toLowerCase().includes(dependencySearch.toLowerCase())).map((option) => (
                      <option key={option.dependency_id} value={option.dependency_id}>
                        {optionLabel(option)}
                      </option>
                    ))}
                  </Select>
                </Field>

                {selected ? (
                  <div className="rounded-md bg-surface-subtle px-3 py-2 text-meta text-ink-secondary">
                    <p>
                      Currently {formatDays(selected.delay_days)} late · {selected.status} ·{" "}
                      {selected.criticality} criticality
                    </p>
                    <p className="mt-0.5">
                      {selected.predecessor_type} {selected.predecessor_id} → {selected.successor_type}{" "}
                      {selected.successor_id}
                      {selected.relationship_type
                        ? ` · ${selected.relationship_type} · ${formatDays(selected.lag_days ?? 0)} lag`
                        : " · relationship timing not recorded"}
                    </p>
                  </div>
                ) : null}

                <Field
                  label="Additional delay"
                  htmlFor="delay"
                  hint="Days on top of the delay already recorded."
                  {...(formError ? { error: formError } : {})}
                >
                  <TextInput
                    id="delay"
                    type="number"
                    min={1}
                    max={365}
                    step={1}
                    value={delayDays}
                    onChange={(event) => { setDelayDays(Number(event.target.value)); setFormError(null); }}
                  />
                </Field>

                <div>
                  <p className="mb-1.5 text-meta font-medium text-ink-secondary">Common cases</p>
                  <div
                    className="grid grid-cols-3 gap-1.5 sm:grid-cols-6 lg:grid-cols-3"
                    role="group"
                    aria-label="Delay presets"
                  >
                    {[5, 10, 30, 90, 180, 365].map((days) => (
                      <Button
                        key={days}
                        size="sm"
                        variant={delayDays === days ? "primary" : "secondary"}
                        onClick={() => { setDelayDays(days); setFormError(null); }}
                        aria-pressed={delayDays === days}
                      >
                        {days}d
                      </Button>
                    ))}
                  </div>
                </div>

                <p className="rounded-control border border-line bg-surface-subtle p-2.5 text-meta text-ink-secondary">
                  Dates and scores are calculated from the dependency graph and recorded project
                  facts. No predictive machine-learning model generates these figures.
                </p>

                <ProgressFoldButton
                  variant="primary"
                  className="w-full"
                  onClick={run}
                  status={runScenario.isPending || runSensitivity.isPending ? "loading" : "idle"}
                  progressLabel="Calculating scenario and sensitivity"
                  disabled={runScenario.isPending || runSensitivity.isPending || dependencies.isLoading || !selected}
                >
                  {runScenario.isPending || runSensitivity.isPending ? "Calculating" : "Run scenario"}
                </ProgressFoldButton>
              </>
            )}
          </CardBody>
        </Card>

        <div className="min-w-0">
          {result && isDraftChanged ? <p role="status" className="mb-4 rounded-control border border-warn bg-warn-tint p-3 text-body text-warn">Inputs changed. The result below still represents +{result.additional_delay_days} days on {result.dependency_name}. Run again to update it.</p> : null}
          {runScenario.isError ? (
            <Card>
              <ErrorState error={runScenario.error} onRetry={run} />
            </Card>
          ) : runScenario.isPending ? <><LoadingRegion label="Calculating scenario"/><SkeletonCards count={2}/></> : !result ? (
            <Card>
              <EmptyState
                title="What would change if this handoff slipped?"
                description="Start with a recorded dependency. The comparison will separate completion dates, local delivery movement and score effects—so a flat score cannot hide a later finish."
              />
            </Card>
          ) : (
            <div className="space-y-4">
              {result.decision_brief && result.decision_brief.length > 0 ? <section className="scenario-brief" aria-labelledby="decision-brief-title">
                <header><span className="scenario-brief-icon"><ScanLine size={22} aria-hidden="true" /></span><div><p className="text-meta text-teal">Decision brief · calculated from records</p><h2 id="decision-brief-title">What this change means</h2></div><span className="scenario-run-label">+{result.additional_delay_days} calendar days</span></header>
                <ol>{result.decision_brief.map((insight, index) => <li key={`${insight.kind}-${insight.project_id}-${index}`} data-kind={insight.kind}>
                  <h3>{insight.headline}</h3><p>{insight.detail}</p><SourceList ids={insight.source_ids} label="Evidence" className="mt-2" />
                </li>)}</ol>
              </section> : null}
              <section className="rounded-card border border-teal bg-teal-tint p-5" aria-label="Calculated delivery outcome">
                <p className="text-meta font-medium text-teal">Calculated result · baseline records unchanged</p>
                {result.affected_projects.map(project=><div key={project.project_id} className="mt-3">
                  <h2 className="text-section font-medium">{project.project_name}</h2>
                  <p className="mt-1 text-body">{!project.baseline_forecast_end_date ? "No recorded completion date to compare" : project.forecast_end_shift_days>0?`${formatDays(project.forecast_end_shift_days)} later completion`:"Recorded completion date unchanged"}</p>
                  <p className="mt-1 text-meta text-ink-secondary">Baseline {formatDate(project.baseline_forecast_end_date)} · Scenario {formatDate(project.scenario_forecast_end_date)}</p>
                </div>)}
                <SourceList ids={result.source_ids} label="Supporting records" className="mt-3"/>
              </section>
              <MethodologyPopover title="Baseline and scenario timeline"><ScenarioTimeline projects={result.affected_projects}/></MethodologyPopover>
              {selected ? <MethodologyPopover title="Affected dependency"><DependencyHandoffs dependencies={[selected]}/></MethodologyPopover> : null}
              <Card>
                <CardHeader
                  title={result.dependency_name}
                  description={`Baseline delay ${formatDays(result.baseline_delay_days)}, modelled at ${formatDays(
                    result.scenario_delay_days,
                  )}`}
                />
                <CardBody>
                  <p className="text-body text-ink-secondary">{result.explanation}</p>
                  {result.assumptions_or_limitations.length > 0 ? (
                    <details className="disclosure mt-3"><summary>Assumptions and limitations · {result.assumptions_or_limitations.length} notes</summary><ul className="list-disc space-y-1 p-4 pl-8 text-meta text-ink-secondary">
                      {result.assumptions_or_limitations.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul></details>
                  ) : null}
                  <SourceList ids={result.source_ids} className="mt-3" label="Calculated from" />
                  <div className="mt-4 border-t border-line pt-3">
                    <ProgressFoldButton
                      variant="secondary"
                      status={explainScenario.isPending ? "loading" : "idle"}
                      progressLabel="Explaining the calculated result"
                      onClick={() =>
                        explainScenario.mutate({
                          dependency_id: result.dependency_id,
                          additional_delay_days: result.additional_delay_days,
                        })
                      }
                      disabled={explainScenario.isPending}
                    >
                      <Sparkles size={16} aria-hidden="true" />
                      {explainScenario.isPending ? "Explaining" : "Explain with AI"}
                    </ProgressFoldButton>
                    <p className="mt-1.5 text-meta text-purple">
                      AI explains the calculated result; it cannot change dates, scores, or records.
                    </p>
                  </div>
                </CardBody>
              </Card>

              {explainScenario.isError ? (
                <Card>
                  <ErrorState
                    error={explainScenario.error}
                    onRetry={() =>
                      explainScenario.mutate({
                        dependency_id: result.dependency_id,
                        additional_delay_days: result.additional_delay_days,
                      })
                    }
                  />
                </Card>
              ) : explainScenario.data ? (
                <Card className={explainScenario.data.status === "ok" ? "border-purple bg-purple-tint" : "border-warn bg-warn-tint"}>
                  <CardHeader
                    title={explainScenario.data.status === "ok" ? "AI decision-support explanation" : "AI explanation unavailable"}
                    description="Narrative only; the figures remain deterministic"
                  />
                  <CardBody>
                    <p className="mb-3 text-meta font-medium text-purple">{explainScenario.data.disclaimer}</p>
                    <p className="text-body text-ink">{explainScenario.data.executive_summary}</p>
                    {explainScenario.data.key_findings.length > 0 ? (
                      <div className="mt-4">
                        <p className="text-meta font-medium text-ink">What it means</p>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-meta text-ink-secondary">
                          {explainScenario.data.key_findings.map((finding) => (
                            <li key={finding}>{finding}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {explainScenario.data.recommended_actions.length > 0 ? (
                      <div className="mt-4">
                        <p className="text-meta font-medium text-ink">Questions for review</p>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-meta text-ink-secondary">
                          {explainScenario.data.recommended_actions.map((action) => (
                            <li key={action}>{action}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <SourceList
                      ids={explainScenario.data.source_ids}
                      className="mt-2"
                      label="AI cited"
                    />
                  </CardBody>
                </Card>
              ) : null}

              {result.schedule_movements.length > 0 ? (
                <Card>
                  <CardHeader
                    title="What moves"
                    description="Each record the delay reaches, and the dependency that carries it there"
                  />
                  <CardBody>
                    <div className="overflow-x-auto">
                      <table className="w-full text-meta">
                        <thead>
                          <tr className="border-b border-line text-left text-ink-secondary">
                            <th className="pb-2 pr-3 font-medium">Record</th>
                            <th className="pb-2 pr-3 font-medium">From</th>
                            <th className="pb-2 pr-3 font-medium">To</th>
                            <th className="pb-2 pr-3 font-medium">Slip</th>
                            <th className="pb-2 font-medium">Carried by</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.schedule_movements.map((movement) => (
                            <tr key={movement.record_id} className="border-b border-line/50">
                              <td className="py-2 pr-3">
                                <span className="font-medium">{movement.record_name}</span>{" "}
                                <code className="text-ink-secondary">{movement.record_id}</code>
                              </td>
                              <td className="py-2 pr-3 tabular-nums">
                                {formatDate(movement.original_date)}
                              </td>
                              <td className="py-2 pr-3 font-medium tabular-nums text-critical">
                                {formatDate(movement.scenario_date)}
                              </td>
                              <td className="py-2 pr-3 tabular-nums">
                                {formatDays(movement.shift_days)}
                              </td>
                              <td className="py-2 text-ink-secondary">
                                {movement.controlling_dependency_id ? (
                                  <code>{movement.controlling_dependency_id}</code>
                                ) : (
                                  "Directly delayed"
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardBody>
                </Card>
              ) : null}

              {runSensitivity.isPending ? (
                <Card>
                  <CardHeader
                    title="Delay sensitivity"
                    description="Calculating the same scenario at seven governed delay points"
                  />
                  <CardBody>
                    <p className="text-meta text-ink-secondary">Calculating response curve…</p>
                  </CardBody>
                </Card>
              ) : runSensitivity.isError ? (
                <Card>
                  <ErrorState
                    error={runSensitivity.error}
                    onRetry={() =>
                      runSensitivity.mutate({
                        intervention_type: "dependency_delay",
                        target_id: selectedId,
                      })
                    }
                  />
                </Card>
              ) : runSensitivity.data ? (
                <Card>
                  <CardHeader
                    title="Delay sensitivity"
                    description="Seven deterministic reruns show when float is consumed and outcomes move"
                  />
                  <CardBody>
                    <ScenarioResponseChart data={runSensitivity.data} />
                    <ul className="mt-3 space-y-1 text-meta text-ink-secondary">
                      {runSensitivity.data.thresholds.map((threshold) => (
                        <li key={threshold.outcome}>{threshold.explanation}</li>
                      ))}
                    </ul>
                  </CardBody>
                </Card>
              ) : null}

              {result.affected_projects.length === 0 ? (
                <Card>
                  <EmptyState
                    title="No affected project result returned"
                    description="Review the calculation notes. No unchanged health band or completion date is inferred from an empty result."
                    className="py-8"
                  />
                </Card>
              ) : (
                result.affected_projects.map((project) => (
                  <Card key={project.project_id}>
                    <CardHeader
                      title={project.project_name}
                      description={project.project_id}
                      action={
                        <Link
                          to={`/projects/${project.project_id}`}
                          className="text-meta font-medium text-accent hover:underline"
                        >
                          Open project
                        </Link>
                      }
                    />
                    <CardBody>
                      <div
                        className={cn(
                          "mb-4 rounded-md border p-4",
                          project.forecast_end_shift_days > 0
                            ? "border-critical/30 bg-critical-tint"
                            : "border-line bg-surface-subtle",
                        )}
                      >
                        <p className="text-meta font-medium uppercase text-ink-secondary">
                          Delivery outcome
                        </p>
                        {!project.baseline_forecast_end_date ? (
                          <p className="mt-1 text-section font-semibold text-ink">No recorded completion date to compare</p>
                        ) : project.forecast_end_shift_days > 0 ? (
                          <p className="mt-1 text-section font-semibold text-ink">
                            Completion moves {formatDays(project.forecast_end_shift_days)} later
                          </p>
                        ) : (
                          <p className="mt-1 text-section font-semibold text-ink">
                            Recorded completion date does not move
                          </p>
                        )}
                        <p className="mt-1 text-meta text-ink-secondary">
                          {formatDate(project.baseline_forecast_end_date)} →{" "}
                          {formatDate(project.scenario_forecast_end_date)}
                        </p>
                      </div>

                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <ComparisonRow
                          label="Overall health"
                          baseline={project.baseline_health_score}
                          baselineBand={project.baseline_health_band}
                          scenario={project.scenario_health_score}
                          scenarioBand={project.scenario_health_band}
                          delta={project.health_score_delta}
                        />
                        <ComparisonRow
                          label="Confidence"
                          baseline={project.baseline_confidence_score}
                          baselineBand={project.baseline_confidence_band}
                          scenario={project.scenario_confidence_score}
                          scenarioBand={project.scenario_confidence_band}
                          delta={project.confidence_score_delta}
                        />
                      </div>

                      {project.factor_deltas.some((factor) => factor.score_delta !== 0) ? (
                        <div className="mt-4 border-t border-line pt-3">
                          <p className="text-meta font-medium">What moved the score</p>
                          <p className="mt-1 text-meta text-ink-secondary">
                            Factor scores run from 0 to 100; higher is healthier. The contribution
                            shows how much each weighted factor changes the overall project score.
                          </p>
                          <ul className="mt-2 space-y-1">
                            {project.factor_deltas
                              .filter((factor) => factor.score_delta !== 0)
                              .map((factor) => (
                                <li
                                  key={factor.factor}
                                  className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 text-meta"
                                >
                                  <span>
                                    {factor.factor_label}{" "}
                                    <span className="text-ink-secondary">
                                      ({Math.round(factor.weight * 100)}% weight)
                                    </span>
                                  </span>
                                  <span className="text-right tabular-nums">
                                    <span>
                                      {formatScore(factor.baseline_score)} →{" "}
                                      {formatScore(factor.scenario_score)}{" "}
                                    </span>
                                    <span
                                      className={cn(
                                        "font-medium",
                                        factor.score_delta < 0 ? "text-critical" : "text-teal",
                                      )}
                                    >
                                      {formatDelta(factor.score_delta)}
                                    </span>
                                    <span className="ml-2 text-ink-secondary">
                                      contributes {formatDelta(factor.weighted_contribution)}
                                    </span>
                                  </span>
                                </li>
                              ))}
                          </ul>
                          <div className="mt-4">
                            <ScenarioFactorWaterfall factors={project.factor_deltas} baseline={project.baseline_health_score} scenario={project.scenario_health_score} />
                          </div>
                        </div>
                      ) : null}

                      {project.new_alert_ids.length > 0 ||
                      project.resolved_alert_ids.length > 0 ||
                      project.changed_alert_ids.length > 0 ? (
                        <div className="mt-4 space-y-1.5 border-t border-line pt-3 text-meta">
                          {project.new_alert_ids.length > 0 ? (
                            <p className="text-critical">
                              {project.new_alert_ids.length} new{" "}
                              {project.new_alert_ids.length === 1 ? "alert" : "alerts"} would be raised.
                            </p>
                          ) : null}
                          {project.resolved_alert_ids.length > 0 ? (
                            <p className="text-ok">
                              {project.resolved_alert_ids.length}{" "}
                              {project.resolved_alert_ids.length === 1 ? "alert" : "alerts"} would clear.
                            </p>
                          ) : null}
                          {project.changed_alert_ids.length > 0 ? (
                            <p className="text-warn">
                              {project.changed_alert_ids.length}{" "}
                              {project.changed_alert_ids.length === 1 ? "alert" : "alerts"} would
                              change severity.
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </CardBody>
                  </Card>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ComparisonRow({
  label,
  baseline,
  baselineBand,
  scenario,
  scenarioBand,
  delta,
}: {
  label: string;
  baseline: number;
  baselineBand: string;
  scenario: number;
  scenarioBand: string;
  delta: number;
}): JSX.Element {
  return (
    <div className="rounded-md border border-line p-3">
      <p className="text-meta font-medium uppercase tracking-wide text-ink-secondary">{label}</p>
      <div className="mt-2 flex items-center gap-3">
        <div>
          <p className="text-meta text-ink-secondary">Now</p>
          <p className="text-body font-semibold text-ink" data-numeric>
            {formatScore(baseline)}
          </p>
          <StatusBadge
            label={baselineBand}
            tone={label === "Confidence" ? confidenceTone(baselineBand) : healthTone(baselineBand)}
            className="mt-1"
          />
        </div>
        <span aria-hidden="true" className="text-ink-secondary">
          →
        </span>
        <div>
          <p className="text-meta text-ink-secondary">Modelled</p>
          <p className="text-body font-semibold text-ink" data-numeric>
            {formatScore(scenario)}
          </p>
          <StatusBadge
            label={scenarioBand}
            tone={label === "Confidence" ? confidenceTone(scenarioBand) : healthTone(scenarioBand)}
            className="mt-1"
          />
        </div>
        <span
          className={cn(
            "ml-auto text-body font-semibold",
            delta < 0 ? "text-critical" : delta > 0 ? "text-ok" : "text-ink-secondary",
          )}
          data-numeric
        >
          {formatDelta(delta)}
        </span>
      </div>
      <p className="mt-2 text-meta text-ink-secondary">
        {label === "Confidence"
          ? "0–100 evidence-quality index. High ≥80, Medium ≥60, Low <60."
          : "0–100 weighted delivery index. Green ≥80, Amber ≥60, Red <60."}
      </p>
    </div>
  );
}
