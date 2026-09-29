import { useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatScore } from "@/lib/format";
import type { ProjectSummary } from "@/types/api";

const BAND_COLOURS: Record<string, string> = {
  Green: "var(--ok)",
  Amber: "var(--warn)",
  Red: "var(--critical)",
};

/** Projects ranked by the health score the API calculated, weakest first. */
export function ProjectHealthBars({ projects, onSelect }: { projects: ProjectSummary[]; onSelect?: (id: string) => void }): JSX.Element {
  const navigate = useNavigate();
  const data = projects
    .filter(project => project.assessment?.is_assessed !== false)
    .slice()
    .sort((left, right) => left.health_score - right.health_score)
    .map((project) => ({
      id: project.project_id,
      fullName: project.project_name,
      name: project.project_name.length > 26 ? `${project.project_name.slice(0, 25)}…` : project.project_name,
      score: project.health_score,
      band: project.health_band,
    }));

  return (
    <div>
    <div style={{ height: Math.max(200, data.length * 34 + 24) }} role="img" aria-label="Project health scores, lowest first, zero to one hundred">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 8 }}>
          <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={168}
            tick={{ fontSize: 12, fill: "var(--text-secondary)" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "var(--surface-subtle)" }}
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null;
              const row = payload[0]?.payload as { fullName: string; score: number; band: string } | undefined;
              if (!row) return null;
              return (
                <div className="rounded-md border border-line bg-surface px-2.5 py-2 text-meta shadow-card">
                  <p className="max-w-xs font-medium text-ink">{row.fullName}</p>
                  <p className="text-ink-secondary" data-numeric>
                    Health {formatScore(row.score)} · {row.band}
                  </p>
                </div>
              );
            }}
          />
          <Bar
            dataKey="score"
            radius={[0, 3, 3, 0]}
            barSize={18}
            isAnimationActive={false}
            className="cursor-pointer"
            onClick={(entry: unknown) => {
              const row = entry as { id?: string } | undefined;
              if (row?.id) { if (onSelect) onSelect(row.id); else navigate(`/projects/${row.id}`); }
            }}
          >
            {data.map((row) => (
              <Cell key={row.id} fill={BAND_COLOURS[row.band] ?? "var(--domain-schedule)"} />
            ))}
            <LabelList
              dataKey="score"
              position="right"
              formatter={(value: number) => formatScore(value)}
              style={{ fontSize: 11, fill: "var(--text-secondary)" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
    <details className="mt-2 text-meta text-ink-secondary">
      <summary className="cursor-pointer text-accent">View ranked health data</summary>
      <table className="mt-2 w-full text-left"><caption className="sr-only">Projects ranked by health</caption>
        <thead><tr><th scope="col">Project</th><th scope="col">Health / 100</th><th scope="col">Band</th></tr></thead>
        <tbody>{data.map(row=><tr key={row.id} className="border-t border-line"><td><button type="button" className="min-h-9 text-accent hover:underline" onClick={()=>onSelect ? onSelect(row.id) : navigate(`/projects/${row.id}`)}>{row.fullName}</button></td><td>{formatScore(row.score)}</td><td>{row.band}</td></tr>)}</tbody>
      </table>
    </details>
    </div>
  );
}
