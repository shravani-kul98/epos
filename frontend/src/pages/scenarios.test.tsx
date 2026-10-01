import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScenariosPage } from "@/pages/scenarios";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(
  tokenResponse({ permissions: ["portfolio.read", "scenario.run", "copilot.ask"] }),
).user;

const DEPENDENCY = {
  dependency_id: "D-2002",
  project_id: "P-002",
  predecessor_type: "Task",
  predecessor_id: "T-2001",
  successor_type: "Task",
  successor_id: "T-2002",
  dependency_name: "Baseline data before negotiation",
  relationship_type: "Finish-to-Start",
  lag_days: 0,
  schedule_data_complete: true,
  status: "On Track",
  delay_days: 0,
  criticality: "High",
};

const SCENARIO = {
  scenario_type: "dependency_delay",
  dependency_id: "D-2002",
  dependency_name: "Baseline data before negotiation",
  additional_delay_days: 90,
  baseline_delay_days: 0,
  scenario_delay_days: 90,
  affected_projects: [
    {
      project_id: "P-002",
      project_name: "Supplier Decarbonisation Programme",
      baseline_health_score: 50.7,
      baseline_health_band: "Red",
      scenario_health_score: 51,
      scenario_health_band: "Red",
      health_score_delta: 0.3,
      baseline_confidence_score: 82,
      baseline_confidence_band: "High",
      scenario_confidence_score: 82,
      scenario_confidence_band: "High",
      confidence_score_delta: 0,
      baseline_alert_counts: { critical: 5, high: 2, medium: 0, low: 0 },
      scenario_alert_counts: { critical: 5, high: 2, medium: 0, low: 0 },
      new_alert_ids: [],
      resolved_alert_ids: [],
      changed_alert_ids: [],
      baseline_forecast_end_date: "2026-09-15",
      scenario_forecast_end_date: "2026-11-12",
      forecast_end_shift_days: 58,
      factor_deltas: [
        {
          factor: "dependency_status",
          factor_label: "Dependency Health",
          baseline_score: 80,
          scenario_score: 65,
          score_delta: -15,
          weight: 0.1,
          weighted_contribution: -1.5,
        },
        {
          factor: "task_execution",
          factor_label: "Task Delivery",
          baseline_score: 51,
          scenario_score: 63,
          score_delta: 12,
          weight: 0.15,
          weighted_contribution: 1.8,
        },
      ],
    },
  ],
  explanation: "The completion date moves 58 days later.",
  source_ids: ["D-2002", "T-2002", "P-002"],
  as_of_date: "2026-08-25",
  calculated_at: "2026-08-25T00:00:00Z",
  assumptions_or_limitations: [],
  interventions: [
    {
      intervention_type: "dependency_delay",
      target_id: "D-2002",
      value: 90,
      unit: "calendar days",
      note: null,
    },
  ],
  schedule_movements: [
    {
      record_type: "Task",
      record_id: "T-2002",
      record_name: "Negotiate decarbonisation commitments",
      original_date: "2026-08-14",
      scenario_date: "2026-11-12",
      shift_days: 90,
      controlling_dependency_id: null,
      controlling_predecessor_id: null,
      propagation_hop: 0,
    },
  ],
  calculation_version: "2.0",
  decision_brief: [{ kind: "schedule", headline: "Review the later finish", detail: "The dependency reaches the recorded delivery date.", project_id: "P-002", source_ids: ["D-2002", "P-002"] }],
};

const SENSITIVITY = {
  intervention_type: "dependency_delay",
  target_id: "D-2002",
  project_id: "P-002",
  unit: "calendar days",
  tested_values: [1, 5, 10, 30, 90, 180, 365],
  health_scores: [49.2, 49.2, 49.2, 51, 51, 51, 51],
  forecast_shift_days: [0, 0, 0, 0, 58, 148, 333],
  is_responsive: true,
  saturated_at_value: null,
  thresholds: [
    {
      outcome: "The project forecast end date moves",
      occurs_at_value: 90,
      unit: "calendar days",
      tested_values: [1, 5, 10, 30, 90, 180, 365],
      explanation: "The project forecast end date first moves at 90 calendar days.",
    },
  ],
  assumptions_or_limitations: [],
};

const AI_EXPLANATION = {
  status: "ok",
  matched_intent: "scenario_explanation",
  matched_question: "Explain this calculated scenario.",
  executive_summary: "Completion moves 58 days later; review the controlling dependency.",
  key_findings: ["Task T-2002 moves from August to November."],
  recommended_actions: ["Ask whether the recorded float can be protected."],
  source_ids: ["SCENARIO-D-2002-90D", "T-2002"],
  human_review_required: true,
  disclaimer: "AI-generated decision-support draft; human review required.",
  warnings: [],
  evidence: [],
  suggested_questions: [],
};

function mockApi(sensitivity: unknown = SENSITIVITY) {
  return vi.fn().mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes("/auth/me")) return ok(PROFILE);
    if (path.includes("/scenarios/dependencies")) return ok([DEPENDENCY]);
    if (path.includes("/scenarios/explain")) return ok(AI_EXPLANATION);
    if (path.includes("/scenarios/dependency-delay")) return ok(SCENARIO);
    if (path.includes("/scenarios/sensitivity")) return ok(sensitivity);
    return ok({});
  });
}

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

describe("ScenariosPage", () => {
  it("shows the engine decision brief and flags changed draft inputs", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Run scenario" }));
    expect(await screen.findByRole("heading", { name: "What this change means" })).toBeInTheDocument();
    expect(screen.getByText("Review the later finish")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Additional delay"));
    await user.type(screen.getByLabelText("Additional delay"), "30");
    expect(screen.getByText(/Inputs changed/)).toHaveTextContent("still represents +90 days");
  });
  it("leads with completion movement rather than a saturated score", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();

    await user.clear(await screen.findByLabelText("Additional delay"));
    await user.type(screen.getByLabelText("Additional delay"), "90");
    await user.click(screen.getByRole("button", { name: "Run scenario" }));

    expect(await screen.findByText("Completion moves 58 days later")).toBeInTheDocument();
    expect(screen.getByText("15 Sep 2026 → 12 Nov 2026")).toBeInTheDocument();
  });

  it("explains raw factor points and their weighted overall contribution", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Run scenario" }));

    expect(await screen.findByText(/Factor scores run from 0 to 100/)).toBeInTheDocument();
    expect(screen.getAllByText(/Task Delivery/).length).toBeGreaterThan(0);
    expect(screen.getByText(/contributes \+1.8/)).toBeInTheDocument();
    expect(screen.getByText(/15% weight/)).toBeInTheDocument();
  });

  it("shows the deterministic response curve and its table fallback", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Run scenario" }));

    expect(await screen.findByText("Delay sensitivity")).toBeInTheDocument();
    expect(screen.getByText(/first moves at 90 calendar days/)).toBeInTheDocument();
    expect(screen.getByText("View sensitivity data as table")).toBeInTheDocument();
    expect(screen.getByText("View score data as table")).toBeInTheDocument();
  });

  it("keeps the AI explanation separate and marked for human review", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Run scenario" }));
    await user.click(await screen.findByRole("button", { name: "Explain with AI" }));

    expect(await screen.findByText("AI decision-support explanation")).toBeInTheDocument();
    expect(screen.getByText(/Completion moves 58 days later; review/)).toBeInTheDocument();
    expect(
      screen.getByText("AI-generated decision-support draft; human review required."),
    ).toBeInTheDocument();
    expect(screen.getByText("Delivery outcome")).toBeInTheDocument();
  });

  it("rejects fractional delay input instead of silently rounding it",async()=>{
    const fetchMock=mockApi();vi.stubGlobal("fetch",fetchMock);
    renderWithProviders(<ScenariosPage/>);
    const user=userEvent.setup();
    await screen.findByRole("option",{name:/D-2002/});
    await user.clear(screen.getByLabelText("Additional delay"));
    await user.type(screen.getByLabelText("Additional delay"),"1.5");
    await user.click(screen.getByRole("button",{name:"Run scenario"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("whole number");
    expect(fetchMock.mock.calls.some(([url])=>String(url).includes("/dependency-delay"))).toBe(false);
  });

  it("never invents zeroes when sensitivity arrays do not align", async () => {
    vi.stubGlobal(
      "fetch",
      mockApi({ ...SENSITIVITY, health_scores: [49.2], forecast_shift_days: [0, 0] }),
    );
    renderWithProviders(<ScenariosPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Run scenario" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sensitivity data is incomplete",
    );
    expect(screen.queryByText("View sensitivity data as table")).not.toBeInTheDocument();
  });
});