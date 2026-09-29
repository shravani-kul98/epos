import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { chartToken, DOMAIN_COLOURS, tooltipStyle } from "@/lib/chart-theme";
import { formatDelta, formatScore } from "@/lib/format";
import type { ScenarioFactorDelta, ScenarioSensitivity } from "@/types/api";

export function ScenarioFactorWaterfall({
  factors,
  baseline,
  scenario,
}: {
  factors: ScenarioFactorDelta[];
  baseline?: number;
  scenario?: number;
}): JSX.Element {
  const data = factors
    .filter((factor) => factor.weighted_contribution !== 0)
    .map((factor) => ({
      name: factor.factor_label,
      contribution: factor.weighted_contribution,
      rawDelta: factor.score_delta,
      weight: Math.round(factor.weight * 100),
    }));

  if (data.length === 0) return <p className="text-meta text-ink-secondary">No score factor moved.</p>;
  const barWidth=50;
  const gap=24;
  const height=180;
  const width=(data.length+2)*(barWidth+gap)+30;
  const scale=height/100;
  let connector=height-(baseline??0)*scale;
  const steps=data.map(item=>{
    const from=connector;
    connector-=item.contribution*scale;
    return {...item,y:Math.min(from,connector),height:Math.max(1,Math.abs(from-connector)),end:connector};
  });

  return (
    <div>
      {baseline!==undefined&&scenario!==undefined ? <div className="overflow-x-auto" role="region" aria-label="Score factor waterfall" tabIndex={0}>
        <svg role="img" aria-label="Baseline health, supplied weighted factor movements, and scenario health" viewBox={`0 0 ${width} ${height+90}`} className="w-full min-w-[360px]">
          <line x1="0" y1={height+10} x2={width} y2={height+10} stroke="var(--border)"/>
          <rect x="10" y={10+height-baseline*scale} width={barWidth} height={baseline*scale} rx="3" fill="var(--domain-governance)"/>
          <text x="35" y={height+34} textAnchor="middle" fontSize="12" fill="var(--text-secondary)">Baseline</text>
          <text x="35" y={height+54} textAnchor="middle" fontSize="12" fill="var(--text)">{formatScore(baseline)}</text>
          {steps.map((step,index)=>{const x=10+(index+1)*(barWidth+gap);return <g key={step.name}>
            <title>{`${step.name}: ${formatDelta(step.contribution)} supplied health points`}</title>
            <rect x={x} y={step.y+10} width={barWidth} height={step.height} fill={step.contribution<0?"var(--critical)":"var(--teal)"}/>
            <line x1={x+barWidth} y1={step.end+10} x2={x+barWidth+gap} y2={step.end+10} stroke="var(--text-muted)" strokeDasharray="3 3"/>
            <text x={x+barWidth/2} y={height+34} textAnchor="middle" fontSize="12" fill="var(--text-secondary)">Factor {index+1}</text>
            <text x={x+barWidth/2} y={height+54} textAnchor="middle" fontSize="12" fill="var(--text)">{formatDelta(step.contribution)}</text>
          </g>;})}
          <rect x={10+(data.length+1)*(barWidth+gap)} y={10+height-scenario*scale} width={barWidth} height={scenario*scale} rx="3" fill="var(--domain-scenarios)"/>
          <text x={35+(data.length+1)*(barWidth+gap)} y={height+34} textAnchor="middle" fontSize="12" fill="var(--text-secondary)">Scenario</text>
          <text x={35+(data.length+1)*(barWidth+gap)} y={height+54} textAnchor="middle" fontSize="12" fill="var(--text)">{formatScore(scenario)}</text>
        </svg>
        <ol className="mb-3 list-decimal space-y-1 pl-5 text-meta text-ink-secondary">{data.map(item=><li key={item.name}>{item.name}: {formatDelta(item.contribution)} weighted health points</li>)}</ol>
        <p className="text-meta text-ink-secondary">Zero-based 0–100 health scale. Connector positions stack supplied contributions; the final health score is the API result, not a browser calculation.</p>
      </div> : null}
      <div className="h-56" role="img" aria-label="Weighted contribution to overall health score">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 28, bottom: 16, left: 12 }}>
            <CartesianGrid stroke={chartToken.grid} strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: chartToken.axisText }}
              axisLine={{ stroke: chartToken.axis }}
              label={{
                value: "Contribution to overall health",
                position: "insideBottom",
                offset: -8,
                style: { fontSize: 11, fill: chartToken.axisText },
              }}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={142}
              tick={{ fontSize: 11, fill: chartToken.label }}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceLine x={0} stroke={chartToken.label} />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value: number, _name: string, item) => {
                const row = item.payload as { rawDelta: number; weight: number };
                return [
                  `${formatDelta(value)} overall (${formatDelta(row.rawDelta)} factor points × ${row.weight}% weight)`,
                  "Effect",
                ];
              }}
            />
            <Bar dataKey="contribution" isAnimationActive={false} radius={[3, 3, 3, 3]}>
              {data.map((item) => (
                <Cell
                  key={item.name}
                  fill={item.contribution < 0 ? "var(--critical)" : "var(--teal)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-meta text-ink-secondary">
        <summary className="cursor-pointer font-medium text-accent">View score data as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="border-b border-line">
              <th className="py-1 font-medium">Factor</th>
              <th className="py-1 text-right font-medium">Factor change</th>
              <th className="py-1 text-right font-medium">Weight</th>
              <th className="py-1 text-right font-medium">Overall contribution</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item) => (
              <tr key={item.name} className="border-b border-line/50">
                <td className="py-1">{item.name}</td>
                <td className="py-1 text-right tabular-nums">{formatDelta(item.rawDelta)}</td>
                <td className="py-1 text-right tabular-nums">{item.weight}%</td>
                <td className="py-1 text-right tabular-nums">{formatDelta(item.contribution)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

export function ScenarioResponseChart({ data }: { data: ScenarioSensitivity }): JSX.Element {
  const lengthsMatch =
    data.tested_values.length > 0 &&
    data.health_scores.length === data.tested_values.length &&
    data.forecast_shift_days.length === data.tested_values.length;
  if (!lengthsMatch) {
    return (
      <p role="alert" className="text-meta text-critical">
        Sensitivity data is incomplete, so no response curve is shown.
      </p>
    );
  }
  const points = data.tested_values.map((delay, index) => ({
    delay,
    health: data.health_scores[index]!,
    finishShift: data.forecast_shift_days[index]!,
  }));

  return (
    <div>
      <div className="h-72" role="img" aria-label="Health and completion response by delay">
        <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={points} margin={{ top: 8, right: 10, bottom: 24, left: 4 }}>
            <CartesianGrid stroke={chartToken.grid} strokeDasharray="3 3" />
            <XAxis
              dataKey="delay"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 11, fill: chartToken.axisText }}
              label={{
                value: "Additional delay (calendar days)",
                position: "insideBottom",
                offset: -12,
                style: { fontSize: 11, fill: chartToken.axisText },
              }}
            />
            <YAxis
              yAxisId="health"
              domain={[0, 100]}
              tick={{ fontSize: 11, fill: chartToken.axisText }}
              label={{
                value: "Health",
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 11, fill: chartToken.axisText },
              }}
            />
            <YAxis
              yAxisId="finish"
              orientation="right"
              allowDecimals={false}
              tick={{ fontSize: 11, fill: chartToken.axisText }}
              label={{
                value: "Finish shift (days)",
                angle: 90,
                position: "insideRight",
                style: { fontSize: 11, fill: chartToken.axisText },
              }}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              labelFormatter={(value: number) => `${value} additional days`}
              formatter={(value: number, name: string) => [
                name === "Health" ? formatScore(value) : `${value} days`,
                name,
              ]}
            />
            <Legend verticalAlign="top" height={28}/>
            <Bar
              yAxisId="finish"
              dataKey="finishShift"
              name="Finish shift"
              fill={DOMAIN_COLOURS.schedule}
              fillOpacity={0.35}
              isAnimationActive={false}
            />
            <Line
              yAxisId="health"
              dataKey="health"
              name="Health"
              stroke="var(--domain-scenarios)"
              strokeWidth={2}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-meta text-ink-secondary">
        <summary className="cursor-pointer font-medium text-accent">View sensitivity data as table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="border-b border-line">
              <th className="py-1 font-medium">Additional delay</th>
              <th className="py-1 text-right font-medium">Health</th>
              <th className="py-1 text-right font-medium">Finish shift</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.delay} className="border-b border-line/50">
                <td className="py-1 tabular-nums">{point.delay} days</td>
                <td className="py-1 text-right tabular-nums">{formatScore(point.health)}</td>
                <td className="py-1 text-right tabular-nums">{point.finishShift} days</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}