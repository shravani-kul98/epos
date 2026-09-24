import { describe, expect, it } from "vitest";

import { daysUntil, formatDate, formatDelta, formatPercent, formatScore, initials } from "@/lib/format";

describe("formatters", () => {
  it("renders a missing date as a dash rather than an empty cell", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
  });

  it("keeps one decimal on scores so the value matches the API", () => {
    expect(formatScore(50.7)).toBe("50.7");
    expect(formatScore(null)).toBe("—");
  });

  it("shows the direction of a scenario change", () => {
    expect(formatDelta(-4.25)).toBe("-4.3");
    expect(formatDelta(3)).toBe("+3");
    expect(formatDelta(0)).toBe("no change");
  });

  it("rounds percentages to whole numbers", () => {
    expect(formatPercent(66.6)).toBe("67%");
  });

  it("reports overdue dates as negative days", () => {
    expect(daysUntil("2026-08-20", "2026-08-25")).toBe(-5);
    expect(daysUntil(null, "2026-08-25")).toBeNull();
  });

  it("builds initials from a full name", () => {
    expect(initials("Priya Raman")).toBe("PR");
    expect(initials("Chen")).toBe("C");
  });
});
