import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioPage } from "@/pages/portfolio";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse()).user;

const PORTFOLIO = {
  as_of_date: "2026-08-25",
  project_count: 2,
  health_bands: { green: 0, amber: 1, red: 1 },
  confidence_bands: { high: 1, medium: 1, low: 0 },
  alert_severities: { critical: 2, high: 1, medium: 3, low: 0 },
  project_phases: { Execution: 1, Validation: 1 },
  project_domains: { "Digital Engineering": 1, Sustainability: 1 },
  projects: [
    {
      project_id: "P-002",
      project_name: "Supplier Decarbonisation Programme",
      domain: "Sustainability",
      project_manager: "Synthetic Manager",
      project_phase: "Execution",
      business_priority: "High",
      forecast_end_date: "2026-09-15",
      health_score: 50.7,
      health_band: "Red",
      confidence_score: 82,
      confidence_band: "High",
      open_alert_count: 5,
      critical_alert_count: 2,
    },
    {
      project_id: "P-007",
      project_name: "Engineering Requirements Digitalisation",
      domain: "Digital Engineering",
      project_manager: "Synthetic Manager",
      project_phase: "Validation",
      business_priority: "Medium",
      forecast_end_date: "2026-10-15",
      health_score: 65,
      health_band: "Amber",
      confidence_score: 70,
      confidence_band: "Medium",
      open_alert_count: 1,
      critical_alert_count: 0,
    },
  ],
  top_alerts: [
    {
      alert_id: "critical_milestone_slip-1",
      project_id: "P-002",
      severity: "Critical",
      alert_type: "critical_milestone_slip",
      alert_type_label: "Milestone forecast to slip",
      title: "Critical milestone forecast slip",
      explanation: "M-202 is forecast later than baseline.",
      source_ids: ["M-202"],
      recommended_next_step: "Review the recovery plan.",
      as_of_date: "2026-08-25",
      detected_at: "2026-08-25T00:00:00Z",
    },
    {
      alert_id: "critical_milestone_slip-2",
      project_id: "P-002",
      severity: "Critical",
      alert_type: "critical_milestone_slip",
      alert_type_label: "Milestone forecast to slip",
      title: "Critical milestone forecast slip",
      explanation: "M-203 is forecast later than baseline.",
      source_ids: ["M-203"],
      recommended_next_step: "Review the recovery plan.",
      as_of_date: "2026-08-25",
      detected_at: "2026-08-25T00:00:00Z",
    },
  ],
};

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("PortfolioPage", () => {
  it("keeps unassessed projects visible without displaying fallback scores", async () => {
    const data = {
      ...PORTFOLIO,
      project_count: 1,
      unassessed_count: 1,
      health_bands: { green: 0, amber: 0, red: 0 },
      confidence_bands: { high: 0, medium: 0, low: 0 },
      top_alerts: [],
      projects: [{ ...PORTFOLIO.projects[0], project_name: "Empty synthetic project", health_score: 75, confidence_score: 58.5, assessment: { is_assessed: false, reason: "Add a milestone or task.", source_ids: ["P-002"] } }],
    };
    vi.stubGlobal("fetch", vi.fn(async (path: string) => ok(path.includes("/auth/me") ? PROFILE : data)));
    renderWithProviders(<PortfolioPage />);
    const row = await screen.findByRole("row", { name: /Empty synthetic project.*Not yet assessed/ });
    expect(within(row).getAllByText("Not yet assessed")).toHaveLength(2);
    expect(within(row).queryByText("75.0")).not.toBeInTheDocument();
    expect(within(row).queryByText("58.5")).not.toBeInTheDocument();
    expect(screen.getByText(/excluded from score charts and band totals/)).toBeInTheDocument();
  });

  it("shows the portfolio distributions returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes("/auth/me")) return ok(PROFILE);
        if (String(url).includes("/analytics/portfolio")) return ok(PORTFOLIO);
        return ok({});
      }),
    );
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText("Confidence bands")).toBeInTheDocument();
    expect(screen.getByText("Alerts by severity")).toBeInTheDocument();
    expect(screen.getByText("Projects by phase")).toBeInTheDocument();
    expect(screen.getByText("Projects by domain")).toBeInTheDocument();
    expect(screen.getAllByText("View data as table").length).toBeGreaterThanOrEqual(5);
  });

  it("renders safely while an older API omits the new distributions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes("/auth/me")) return ok(PROFILE);
        if (String(url).includes("/analytics/portfolio")) {
          return ok({ ...PORTFOLIO, project_phases: undefined, project_domains: undefined });
        }
        return ok({});
      }),
    );
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText("Projects by phase")).toBeInTheDocument();
    expect(screen.getByText("Projects by domain")).toBeInTheDocument();
  });

  it("tells two alerts of the same type apart by the record each cites", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes("/auth/me")) return ok(PROFILE);
        if (String(url).includes("/analytics/portfolio")) return ok(PORTFOLIO);
        return ok({});
      }),
    );
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText(/M-202/)).toBeInTheDocument();
    expect(screen.getByText(/M-203/)).toBeInTheDocument();
  });
});