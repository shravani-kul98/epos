import { useNavigate } from "react-router-dom";
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { formatScore } from "@/lib/format";
import type { ProjectSummary } from "@/types/api";

const BAND_COLOURS: Record<string, string> = {
  Green: "var(--ok)",
  Amber: "var(--warn)",
  Red: "var(--critical)",
};

interface Point {
  x: number;
  y: number;
  z: number;
  id: string;
  name: string;
  band: string;
}

/**
 * Health against confidence. The quadrant matters: a low health score with high confidence is a
 * problem you can act on, while a low score with low confidence means the data must be fixed first.
 */
export function HealthConfidenceScatter({ projects, onSelect }: { projects: ProjectSummary[]; onSelect?: (id: string) => void }): JSX.Element {
  const navigate = useNavigate();
  const assessed = projects.filter(project => project.assessment?.is_assessed !== false);
  const points: Point[] = assessed.map((project) => ({
    x: project.health_score,
    y: project.confidence_score,
    z: project.open_alert_count,
    id: project.project_id,
    name: project.project_name,
    band: project.health_band,
  }));

  return (
    <div>
    <div className="h-72" role="img" aria-label="Project health and reporting confidence, both on a zero to one hundred scale">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 4 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--border)"
            label={{
              value: "Health score",
              position: "insideBottom",
              offset: -12,
              style: { fontSize: 11, fill: "var(--text-muted)" },
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--border)"
            label={{
              value: "Confidence",
              angle: -90,
              position: "insideLeft",
              style: { fontSize: 11, fill: "var(--text-muted)" },
            }}
          />
          <ZAxis type="number" dataKey="z" range={[60, 320]} />
          <ReferenceLine x={60} stroke="var(--border)" />
          <ReferenceLine y={60} stroke="var(--border)" />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null;
              const point = payload[0]?.payload as Point | undefined;
              if (!point) return null;
              return (
                <div className="rounded-md border border-line bg-surface px-2.5 py-2 text-meta shadow-card">
                  <p className="font-medium text-ink">{point.name}</p>
                  <p className="text-ink-secondary" data-numeric>
                    Health {formatScore(point.x)} · Confidence {formatScore(point.y)}
                  </p>
                  <p className="text-ink-secondary" data-numeric>
                    {point.z} open {point.z === 1 ? "alert" : "alerts"}
                  </p>
                </div>
              );
            }}
          />
          <Scatter
            data={points}
            isAnimationActive={false}
            onClick={(point: unknown) => {
              const entry = point as Point | undefined;
              if (entry?.id) { if (onSelect) onSelect(entry.id); else navigate(`/projects/${entry.id}`); }
            }}
            shape="circle"
            fillOpacity={0.85}
            className="cursor-pointer"
          >
            {points.map((point) => (
              <Cell key={point.id} fill={BAND_COLOURS[point.band] ?? "var(--domain-schedule)"} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
    <details className="mt-2 text-meta text-ink-secondary">
      <summary className="cursor-pointer text-accent">View health and confidence data</summary>
      <div className="overflow-x-auto"><table className="mt-2 w-full text-left">
        <caption className="sr-only">Health and confidence by project</caption>
        <thead><tr><th scope="col">Project</th><th scope="col">Health / 100</th><th scope="col">Confidence / 100</th><th scope="col">Open alerts</th></tr></thead>
        <tbody>{assessed.map(project => <tr key={project.project_id} className="border-t border-line">
          <td className="py-2"><button type="button" className="min-h-9 text-accent hover:underline" onClick={() => onSelect ? onSelect(project.project_id) : navigate(`/projects/${project.project_id}`)}>{project.project_name}</button></td>
          <td>{formatScore(project.health_score)}</td><td>{formatScore(project.confidence_score)}</td><td>{project.open_alert_count}</td>
        </tr>)}</tbody>
      </table></div>
    </details>
    </div>
  );
}
