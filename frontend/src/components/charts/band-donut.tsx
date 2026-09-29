import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { tooltipStyle } from "@/lib/chart-theme";

interface Slice {
  name: string;
  value: number;
  colour: string;
}

/**
 * Band distribution. The API returns the tallies; this only draws them. A count is printed in the
 * centre so the chart is still readable when colour is not perceivable.
 */
export function BandDonut({ data, total, caption, onSelect, selected, label = "Project band distribution" }: {
  data: Slice[]; total: number; caption: string;
  onSelect?: (name: string) => void;
  selected?: string;
  label?: string;
}): JSX.Element {
  const populated = data.filter((slice) => slice.value > 0);

  return (
    <div>
      <div className="relative h-48" role="img" aria-label={label}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={populated}
              dataKey="value"
              nameKey="name"
              innerRadius={58}
              outerRadius={82}
              paddingAngle={2}
              strokeWidth={0}
              isAnimationActive={false}
              onClick={(slice: { name?: string }) => { if (slice.name) onSelect?.(slice.name); }}
            >
              {populated.map((slice) => (
                <Cell key={slice.name} fill={slice.colour} stroke="var(--surface)" strokeWidth={selected === slice.name ? 4 : 1} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number, name: string) => [`${value} projects`, name]}
              contentStyle={tooltipStyle}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center">
          <p className="text-kpi font-semibold leading-none text-ink" data-numeric>
            {total}
          </p>
          <p className="mt-1 text-meta text-ink-secondary">{caption}</p>
        </div>
      </div>
      <ul className="flex flex-wrap justify-center gap-2">{data.map((slice) => <li key={slice.name}>
        {onSelect ? <button type="button" aria-pressed={selected === slice.name} aria-label={`Filter by ${slice.name}`} onClick={() => onSelect(slice.name)} className="flex min-h-9 items-center gap-1.5 rounded-control border border-line px-2 text-meta hover:border-accent aria-pressed:border-accent aria-pressed:bg-accent-tint">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: slice.colour }} aria-hidden="true" />{slice.name} <span className="tabular-nums">{slice.value}</span>
        </button> : <span className="flex items-center gap-1.5 text-meta text-ink-secondary"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: slice.colour }} aria-hidden="true" />{slice.name} {slice.value}</span>}
      </li>)}</ul>
      <details className="mt-1 text-meta text-ink-secondary">
        <summary className="cursor-pointer text-center font-medium text-accent">
          View data as table
        </summary>
        <table className="mt-2 w-full text-left">
          <caption className="sr-only">{label}</caption>
          <thead>
            <tr className="border-b border-line">
              <th className="py-1 font-medium">Band</th>
              <th className="py-1 text-right font-medium">Count</th>
            </tr>
          </thead>
          <tbody>
            {data.map((slice) => (
              <tr key={slice.name} className="border-b border-line/50">
                <td className="py-1">{slice.name}</td>
                <td className="py-1 text-right tabular-nums">{slice.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
