import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IssuesPage } from "@/pages/issues";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse()).user;

const PORTFOLIO = {
  as_of_date: "2026-08-25",
  project_count: 1,
  health_bands: { green: 0, amber: 0, red: 1 },
  confidence_bands: { high: 1, medium: 0, low: 0 },
  alert_severities: { critical: 0, high: 0, medium: 0, low: 0 },
  project_phases: {},
  project_domains: {},
  projects: [{ project_id: "P-002", project_name: "Supplier Decarbonisation Programme" }],
  top_alerts: [],
};

const ISSUES = [
  {
    issue_id: "I-2001",
    project_id: "P-002",
    title: "Emission baseline data rejected by two suppliers",
    description: "Two suppliers returned unusable baselines.",
    severity: "Critical",
    owner: "Alex Morgan",
    status: "Open",
    raised_date: "2026-08-10",
    target_resolution_date: "2026-08-20",
    resolution_summary: null,
    resolved_by: null,
    resolved_at: null,
    source_reference: "MTG-2026-08-10",
  },
  {
    issue_id: "I-2002",
    project_id: "P-002",
    title: "Reporting template rejected by audit",
    description: "The template omits a mandatory field.",
    severity: "Medium",
    owner: null,
    status: "Closed",
    raised_date: "2026-07-02",
    target_resolution_date: null,
    resolution_summary: "Template corrected.",
    resolved_by: "Alex Morgan",
    resolved_at: "2026-07-20T00:00:00Z",
    source_reference: null,
  },
];

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

function mockApi(issues: unknown = ISSUES) {
  return vi.fn().mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes("/auth/me")) return ok(PROFILE);
    if (path.includes("/analytics/portfolio")) return ok(PORTFOLIO);
    if (path.includes("/issues")) return ok(issues);
    return ok({});
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("IssuesPage", () => {
  it("lists the register and counts only unresolved issues", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<IssuesPage />);

    expect(await screen.findByText("Emission baseline data rejected by two suppliers")).toBeInTheDocument();
    expect(screen.getByText("Reporting template rejected by audit")).toBeInTheDocument();
    // One of the two is Closed, so it counts towards neither open nor past-target.
    expect(screen.getByText("Open issues").parentElement).toHaveTextContent("1");
    expect(screen.getByText("Past target").parentElement).toHaveTextContent("1");
  });

  it("says so plainly when no issue has been raised", async () => {
    vi.stubGlobal("fetch", mockApi([]));
    renderWithProviders(<IssuesPage />);

    expect(await screen.findByText("No issues recorded")).toBeInTheDocument();
    expect(
      screen.getByText("No project in this workspace has an issue in the register."),
    ).toBeInTheDocument();
  });
});
