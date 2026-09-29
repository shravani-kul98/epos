import { Fragment, useState } from "react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/cn";
import type { Risk } from "@/types/api";

const LEVELS = [1, 2, 3, 4, 5];

interface RiskHeatmapProps {
  risks: Risk[];
  onSelectCell?: (probability: number, impact: number) => void;
  selectedCell?: readonly [number, number] | null;
}

/**
 * Probability against impact, the standard risk grid. Cells hold the stored probability and impact
 * values from the risk register; nothing is recalculated here.
 */
export function RiskHeatmap({ risks, onSelectCell, selectedCell }: RiskHeatmapProps): JSX.Element {
  const [localCell, setLocalCell] = useState<readonly [number, number] | null>(null);
  const selected = onSelectCell ? selectedCell : localCell;
  const grid = new Map<string, Risk[]>();
  for (const risk of risks) {
    const key = `${risk.probability}-${risk.impact}`;
    const bucket = grid.get(key);
    if (bucket) bucket.push(risk);
    else grid.set(key, [risk]);
  }
  const matching = selected ? risks.filter(risk => risk.probability === selected[0] && risk.impact === selected[1]) : risks;

  return (
    <div>
    <p className="mb-3 text-meta text-ink-secondary">Recorded probability and impact. Select a populated cell to inspect its risks.</p>
    <div className="flex gap-2">
      <div className="flex flex-col items-center justify-center pr-1">
        <span className="whitespace-nowrap text-meta text-ink-secondary [writing-mode:vertical-rl] [transform:rotate(180deg)]">
          Probability
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="grid grid-cols-[auto_repeat(5,minmax(0,1fr))] gap-1">
          {[...LEVELS].reverse().map((probability) => (
            <Fragment key={`row-${probability}`}>
              <div
                className="flex items-center justify-end pr-1 text-meta text-ink-secondary"
                data-numeric
              >
                {probability}
              </div>
              {LEVELS.map((impact) => {
                const bucket = grid.get(`${probability}-${impact}`) ?? [];
                return (
                  <button
                    key={`${probability}-${impact}`}
                    type="button"
                    disabled={bucket.length === 0}
                    aria-label={`Probability ${probability}, impact ${impact}: ${bucket.length} ${bucket.length === 1 ? "risk" : "risks"}`}
                    aria-pressed={selected?.[0] === probability && selected?.[1] === impact}
                    onClick={() => {
                      if (onSelectCell) onSelectCell(probability, impact);
                      else setLocalCell(localCell?.[0] === probability && localCell?.[1] === impact ? null : [probability, impact]);
                    }}
                    title={
                      bucket.length === 0
                        ? `No risks at probability ${probability}, impact ${impact}`
                        : bucket.map((risk) => `${risk.risk_id} ${risk.risk_name}`).join("\n")
                    }
                    className={cn(
                      "flex aspect-square min-h-9 items-center justify-center rounded-control border text-body font-medium transition-colors",
                      bucket.length ? "border-accent-border bg-accent-tint text-accent hover:border-accent" : "border-line bg-surface-subtle text-ink-muted",
                      selected?.[0] === probability && selected?.[1] === impact && "ring-2 ring-accent ring-offset-2",
                    )}
                    data-numeric
                  >
                    {bucket.length || null}
                  </button>
                );
              })}
            </Fragment>
          ))}
          <div />
          {LEVELS.map((impact) => (
            <div key={`impact-${impact}`} className="pt-1 text-center text-meta text-ink-secondary" data-numeric>
              {impact}
            </div>
          ))}
        </div>
        <p className="mt-1.5 text-center text-meta text-ink-secondary">Impact</p>
      </div>
    </div>
    <p className="mt-3 text-meta text-ink-muted">Cell values count records; color does not assign a new severity.</p>
    <details className="mt-3 text-meta text-ink-secondary" open={selected ? true : undefined}>
      <summary className="cursor-pointer font-medium text-accent">View risk matrix records{selected ? ` · probability ${selected[0]}, impact ${selected[1]}` : ""}</summary>
      <div className="mt-2 overflow-x-auto"><table className="w-full text-left">
        <caption className="sr-only">Risk matrix records</caption>
        <thead><tr><th scope="col">Risk</th><th scope="col">Probability</th><th scope="col">Impact</th></tr></thead>
        <tbody>{matching.map(risk=><tr key={risk.risk_id} className="border-t border-line"><td className="py-2"><Link className="text-accent hover:underline" to={`/projects/${risk.project_id}?tab=risks`}>{risk.risk_name}</Link><p><code>{risk.risk_id}</code></p></td><td className="tabular-nums">{risk.probability}</td><td className="tabular-nums">{risk.impact}</td></tr>)}</tbody>
      </table></div>
    </details>
    </div>
  );
}

export function RiskHeatmapLegend({ projectId }: { projectId?: string }): JSX.Element {
  return (
    <div className="flex items-center justify-between text-meta text-ink-secondary">
      <span>Count of open risks per cell</span>
      {projectId ? (
        <Link to={`/projects/${projectId}?tab=risks`} className="font-medium text-accent hover:underline">
          Open risk register
        </Link>
      ) : null}
    </div>
  );
}
