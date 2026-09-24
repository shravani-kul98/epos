/**
 * Chart palette.
 *
 * Charts are rendered by a library that needs colour strings rather than class names, so this is
 * the one place allowed to reference token variables directly. Keeping them here means a token
 * rename cannot silently leave a chart unstyled.
 */

export const chartToken = {
  grid: "var(--border)",
  axis: "var(--border)",
  axisText: "var(--text-muted)",
  label: "var(--text-secondary)",
  surface: "var(--surface)",
  hover: "var(--surface-subtle)",
} as const;

/** Health bands keep the same colour wherever they appear. */
export const BAND_COLOURS: Record<string, string> = {
  Green: "var(--ok)",
  Amber: "var(--warn)",
  Red: "var(--critical)",
};

export const CONFIDENCE_COLOURS: Record<string, string> = {
  High: "var(--ok)",
  Medium: "var(--warn)",
  Low: "var(--critical)",
};

/** Series colours for categories that are not a status. */
export const DOMAIN_COLOURS = {
  schedule: "var(--domain-schedule)",
  risk: "var(--domain-risk)",
  quality: "var(--domain-quality)",
  requirements: "var(--domain-requirements)",
  dependencies: "var(--domain-dependencies)",
  testing: "var(--domain-testing)",
  capacity: "var(--domain-capacity)",
  intelligence: "var(--domain-intelligence)",
} as const;

export const CHART_SERIES: string[] = [
  DOMAIN_COLOURS.schedule,
  DOMAIN_COLOURS.capacity,
  DOMAIN_COLOURS.dependencies,
  DOMAIN_COLOURS.quality,
  DOMAIN_COLOURS.risk,
];

/** Shared tooltip container styling, so every chart tooltip reads the same. */
export const tooltipStyle = {
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--surface)",
  color: "var(--text)",
  fontSize: 12,
} as const;
