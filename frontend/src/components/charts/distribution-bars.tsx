import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_SERIES, tooltipStyle } from "@/lib/chart-theme";

interface DistributionItem {
  name: string;
  value: number;
  colour?: string;
}

export function DistributionBars({
  data,
  unit,
  onSelect,
  preserveOrder = false,
}: {
  data: DistributionItem[];
  unit: string;
  onSelect?: (name: string) => void;
  preserveOrder?: boolean;
}): JSX.Element {
  const ordered = preserveOrder ? data : data.slice().sort((left, right) => right.value - left.value || left.name.localeCompare(right.name));

  return (
    <div>
      <div style={{ height: Math.max(180, ordered.length * 34 + 24) }} role="img" aria-label={`${unit} distribution`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={ordered} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 8 }}>
            <XAxis type="number" allowDecimals={false} tickCount={3} tick={{ fontSize: 12, fill: "var(--text-secondary)" }} axisLine={false} tickLine={false} />
            <YAxis
              type="category"
              dataKey="name"
              width={128}
              tick={{ fontSize: 11, fill: "var(--text-secondary)" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              cursor={{ fill: "var(--surface-subtle)" }}
              formatter={(value: number) => [`${value} ${unit}`, unit]}
            />
            <Bar dataKey="value" barSize={17} radius={[0, 3, 3, 0]} isAnimationActive={false} onClick={(item: { name?: string }) => { if (item.name) onSelect?.(item.name); }}>
              {ordered.map((item, index) => (
                <Cell
                  key={item.name}
                  fill={item.colour ?? CHART_SERIES[index % CHART_SERIES.length]}
                />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                style={{ fontSize: 11, fill: "var(--text-secondary)" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-meta text-ink-secondary">
        <summary className="cursor-pointer font-medium text-accent">View data as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="border-b border-line">
              <th className="py-1 font-medium">Category</th>
              <th className="py-1 text-right font-medium">{unit}</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((item) => (
              <tr key={item.name} className="border-b border-line/50">
                <td className="py-1">{onSelect ? <button type="button" className="min-h-9 text-accent hover:underline" onClick={() => onSelect(item.name)}>Filter by {item.name}</button> : item.name}</td>
                <td className="py-1 text-right tabular-nums">{item.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}