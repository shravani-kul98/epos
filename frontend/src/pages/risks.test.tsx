import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RisksPage } from "@/pages/risks";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse()).user;

const PORTFOLIO = {
  as_of_date: "2026-08-25",
  project_count: 2,
  health_bands: { green: 0, amber: 1, red: 1 },
  confidence_bands: { high: 1, medium: 1, low: 0 },
  alert_severities: { critical: 0, high: 0, medium: 0, low: 0 },
  project_phases: {},
  project_domains: {},
  projects: [
    { project_id: "P-002", project_name: "Supplier Decarbonisation Programme" },
    { project_id: "P-007", project_name: "Engineering Requirements Digitalisation" },
  ],
  top_alerts: [],
};

function risk(id: string, projectId: string, name: string) {
  return {
    risk_id: id,
    project_id: projectId,
    risk_name: name,
    probability: 4,
    impact: 5,
    severity_score: 20,
    status: "Open",
    mitigation_owner: null,
    mitigation_status: null,
    due_date: "2026-09-30",
  };
}

const ALL_RISKS = [
  risk("R-2001", "P-002", "Key supplier unable to meet decarbonisation targets"),
  risk("R-7001", "P-007", "Attribute mapping cannot be automated"),
];

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

const requested: string[] = [];

function mockApi() {
  return vi.fn().mockImplementation(async (url: string) => {
    const path = String(url);
    requested.push(path);
    if (path.includes("/auth/me")) return ok(PROFILE);
    if (path.includes("/analytics/portfolio")) return ok(PORTFOLIO);
    if (path.includes("/risks")) {
      const scoped = path.match(/project_id=([^&]+)/);
      return ok(scoped ? ALL_RISKS.filter((r) => r.project_id === scoped[1]) : ALL_RISKS);
    }
    return ok({});
  });
}

beforeEach(() => {
  requested.length = 0;
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("RisksPage", () => {
  it("shows the whole register across projects before any filter is chosen", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<RisksPage />);

    const register = within(await screen.findByRole("region", { name: "Risk register table" }));
    expect(register.getByText("Key supplier unable to meet decarbonisation targets")).toBeInTheDocument();
    expect(register.getByText("Attribute mapping cannot be automated")).toBeInTheDocument();
    expect(requested.some((path) => path.includes("/risks") && !path.includes("project_id"))).toBe(true);
  });

  it("narrows to a single project when one is selected", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<RisksPage />);
    const user = userEvent.setup();

    // The options arrive with the portfolio, so wait for one before choosing it.
    await screen.findByRole("option", { name: /P-007/ });
    await user.selectOptions(screen.getByLabelText("Project"), "P-007");

    await waitFor(() =>
      expect(
        screen.queryByText("Key supplier unable to meet decarbonisation targets"),
      ).not.toBeInTheDocument(),
    );
    expect(within(screen.getByRole("region", { name: "Risk register table" })).getByText("Attribute mapping cannot be automated")).toBeInTheDocument();
  });
});
