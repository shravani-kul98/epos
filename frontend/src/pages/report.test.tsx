import { describe, expect, it } from "vitest";

import { reportAsText } from "@/pages/report";
import type { ExecutiveReport } from "@/types/api";

function report(overrides: Partial<ExecutiveReport> = {}): ExecutiveReport {
  return {
    as_of_date: "2026-08-25",
    window_days: 7,
    generated_at: "2026-08-25T09:00:00Z",
    headline: "Of 9 projects, 6 in red and 1 in amber as at 2026-08-25.",
    project_count: 9,
    health_bands: { green: 2, amber: 1, red: 6 },
    confidence_bands: { high: 3, medium: 4, low: 2 },
    alert_severities: { critical: 4, high: 7, medium: 11, low: 2 },
    sections: [
      {
        key: "attention",
        title: "Projects needing attention",
        summary: "6 projects in the red health band.",
        items: [
          {
            text: "Supplier Data Migration scores 50.7 with 5 open alerts, 2 of them critical.",
            source_ids: ["P-002"],
          },
        ],
      },
    ],
    source_ids: ["P-002"],
    ...overrides,
  };
}

describe("report as text", () => {
  it("leads with the position so a reader gets the answer first", () => {
    const lines = reportAsText(report()).split("\n");

    expect(lines[0]).toBe("Executive report as at 2026-08-25");
    expect(lines[2]).toBe("Of 9 projects, 6 in red and 1 in amber as at 2026-08-25.");
  });

  it("carries the record identifiers behind every statement", () => {
    expect(reportAsText(report())).toContain(
      "- Supplier Data Migration scores 50.7 with 5 open alerts, 2 of them critical. [P-002]",
    );
  });

  it("names each section it copied", () => {
    expect(reportAsText(report())).toContain("PROJECTS NEEDING ATTENTION");
  });

  it("states that the content came from recorded data", () => {
    expect(reportAsText(report())).toContain(
      "Every statement above is drawn from recorded project data.",
    );
  });

  it("copies a report with nothing to say without inventing content", () => {
    const text = reportAsText(report({ sections: [], source_ids: [] }));

    expect(text).toContain("Health: 2 green, 1 amber, 6 red.");
    expect(text).not.toContain("undefined");
  });
});
