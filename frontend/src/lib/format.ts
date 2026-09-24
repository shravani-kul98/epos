import { differenceInCalendarDays, format, parseISO } from "date-fns";

// The API stores UTC without an offset. Reading such a value as local time put two clocks side
// by side on one screen, so a timestamp without an offset is read as UTC.
const NAIVE_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

export function parseServerValue(value: string): Date {
  return parseISO(NAIVE_TIMESTAMP.test(value) ? `${value}Z` : value);
}

/** Format an ISO date as a short, unambiguous label. Invalid input degrades to a dash. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return format(parseServerValue(value), "d MMM yyyy");
  } catch {
    return "—";
  }
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return format(parseServerValue(value), "d MMM yyyy, HH:mm");
  } catch {
    return "—";
  }
}

/** Today in the browser's calendar, as the ISO date a date input and the API expect. */
export function todayIso(): string {
  return format(new Date(), "yyyy-MM-dd");
}

/** One decimal place. `toFixed` rounds halves away from zero, matching `format_score` in Python. */
export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(1);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)}%`;
}

/** Signed delta, so a scenario result reads as a direction of travel. */
export function formatDelta(value: number): string {
  const rounded = Number(value.toFixed(1));
  if (rounded === 0) return "no change";
  return rounded > 0 ? `+${rounded}` : `${rounded}`;
}

export function formatDays(days: number): string {
  const rounded = Math.round(days);
  return `${rounded} ${Math.abs(rounded) === 1 ? "day" : "days"}`;
}

/** Days from the analysis date to a target date. Negative means overdue. */
export function daysUntil(target: string | null | undefined, asOf: string): number | null {
  if (!target) return null;
  try {
    return differenceInCalendarDays(parseISO(target), parseISO(asOf));
  } catch {
    return null;
  }
}

export function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0]?.charAt(0) ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? "") : "";
  return (first + last).toUpperCase();
}
