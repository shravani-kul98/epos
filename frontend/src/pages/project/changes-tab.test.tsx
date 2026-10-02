import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangesTab } from "@/pages/project/changes-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["portfolio.read"] })).user;

const CHANGE_REQUEST = {
  row_version: 3,
  change_request_id: "CR-910",
  project_id: "P-002",
  requirement_id: "REQ-910",
  change_description: "Tighten the synthetic response-time limit",
  reason: "Customer review asked for a lower limit.",
  priority: "Medium",
  status: "Open",
  requested_by: "Test Manager",
  requested_date: "2026-09-20",
};

const IMPACT = {
  change_request_id: "CR-910",
  requirement_id: "REQ-910",
  affected_task_ids: [],
  affected_test_case_ids: [],
  affected_dependency_ids: [],
  affected_milestone_ids: [],
  estimated_schedule_impact_days: 0,
  risk_level: "Low",
  explanation: "No linked records were found for this requirement.",
  source_ids: ["CR-910", "REQ-910"],
  as_of_date: "2026-09-24",
  calculated_at: "2026-09-24T09:00:00Z",
  assumptions_or_limitations: [],
};

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

function mockApi(evidenceStatus: "Assessed" | "Insufficient evidence") {
  return vi.fn(async (input: string) => {
    if (input.includes("/auth/me")) return ok(PROFILE);
    if (input.includes("/impact")) return ok({ ...IMPACT, evidence_status: evidenceStatus });
    return ok([CHANGE_REQUEST]);
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("change impact evidence", () => {
  it("says the impact cannot be assessed instead of showing a risk level", async () => {
    vi.stubGlobal("fetch", mockApi("Insufficient evidence"));
    const user = userEvent.setup();
    renderWithProviders(<ChangesTab projectId="P-002" />);

    await user.click(await screen.findByText(CHANGE_REQUEST.change_description));
    const dialog = within(screen.getByRole("dialog"));
    expect(await dialog.findByText("Insufficient evidence")).toBeInTheDocument();
    expect(dialog.getByText("Not assessed")).toBeInTheDocument();
    expect(dialog.queryByText("0 days")).not.toBeInTheDocument();
    expect(dialog.getByText("Nothing downstream is traced to this requirement yet, so the impact cannot be assessed.")).toBeInTheDocument();
    expect(dialog.queryByText("Low")).not.toBeInTheDocument();
  });

  it("keeps the calculated risk level when the impact was assessed", async () => {
    vi.stubGlobal("fetch", mockApi("Assessed"));
    const user = userEvent.setup();
    renderWithProviders(<ChangesTab projectId="P-002" />);

    await user.click(await screen.findByText(CHANGE_REQUEST.change_description));
    const dialog = within(screen.getByRole("dialog"));
    expect(await dialog.findByText("Low")).toBeInTheDocument();
    expect(dialog.queryByText("Insufficient evidence")).not.toBeInTheDocument();
  });
});
