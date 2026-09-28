import { useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge, type Tone } from "@/components/ui/status-badge";
import { SourceList } from "@/components/ui/source-list";
import { formatScore } from "@/lib/format";
import type { Driver, FactorBreakdown } from "@/types/api";

interface ScoreCardProps {
  title: string;
  score: number;
  band: string;
  tone: Tone;
  factors: FactorBreakdown[];
  drivers?: Driver[];
  sourceIds: string[];
  limitations: string[];
  asOfDate: string;
}

/**
 * Presents a calculated score together with the weighted factors that produced it. Nothing here
 * is computed in the browser: every number shown is a field returned by the API.
 */
export function ScoreCard({
  title,
  score,
  band,
  tone,
  factors,
  drivers = [],
  sourceIds,
  limitations,
  asOfDate,
}: ScoreCardProps): JSX.Element {
  const [showWorking, setShowWorking] = useState(false);

  return (
    <section className="card">
      <header className="card-header">
        <div>
          <h2 className="card-title">{title}</h2>
          <p className="mt-0.5 text-meta text-ink-secondary">Calculated as at {asOfDate}</p>
        </div>
        <Button size="sm" onClick={() => setShowWorking((open) => !open)} aria-expanded={showWorking}>
          {showWorking ? "Hide working" : "Show working"}
        </Button>
      </header>

      <div className="card-body">
        <div className="flex items-end gap-3">
          <span className="text-kpi font-semibold leading-none text-ink" data-numeric>
            {formatScore(score)}
          </span>
          <span className="pb-1 text-meta text-ink-secondary">out of 100</span>
          <StatusBadge label={band} tone={tone} className="mb-1 ml-auto" />
        </div>

        <ul className="mt-5 space-y-3">
          {factors.map((factor) => (
            <li key={factor.key}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-body font-medium text-ink">{factor.label}</span>
                <span className="text-meta text-ink-secondary" data-numeric>
                  {formatScore(factor.score)}
                  <span className="text-ink-secondary"> × {Math.round(factor.weight * 100)}%</span>
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-subtle">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max(0, Math.min(100, factor.score))}%` }}
                  role="presentation"
                />
              </div>
              {showWorking ? (
                <div className="mt-2 rounded-md bg-surface-subtle px-3 py-2">
                  <p className="text-meta text-ink-secondary">{factor.description}</p>
                  <p className="mt-1 text-meta text-ink-secondary" data-numeric>
                    Contributes {formatScore(factor.weighted_contribution)} points to the total.
                  </p>
                  {factor.explanations.length > 0 ? (
                    <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-meta text-ink-secondary">
                      {factor.explanations.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>

        {drivers.length > 0 ? (
          <details className="mt-5 border-t border-line pt-4">
            <summary className="cursor-pointer text-meta font-medium text-ink-secondary">
              What is holding this back
            </summary>
            <ul className="mt-2 space-y-2">
              {drivers.map((driver) => (
                <li key={`${driver.factor_label}-${driver.message}`} className="text-body text-ink">
                  <span className="font-medium">{driver.factor_label}: </span>
                  {driver.message}
                  <p className="mt-0.5 text-meta text-ink-secondary">{driver.score_impact_description}</p>
                  <SourceList ids={driver.source_ids} className="mt-1" />
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        {limitations.length > 0 ? (
          <div className="mt-5 rounded-md border border-line bg-surface-subtle px-3 py-2">
            <h3 className="text-meta font-semibold text-ink-secondary">Assumptions and limits</h3>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-meta text-ink-secondary">
              {limitations.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <SourceList ids={sourceIds} className="mt-4" label="Calculated from" />
      </div>
    </section>
  );
}
