import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangesTab } from "@/pages/project/changes-tab";
import { DecisionsTab } from "@/pages/project/decisions-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(
  tokenResponse({ permissions: ["portfolio.read", "change.read", "change.decide"] }),
).user;

const DECISION = {
  row_version: 7,
  decision_id: "DEC-900",
  project_id: "P-002",
  title: "Approve the synthetic baseline",
  description: "Approve the reviewed synthetic delivery baseline.",
  category: "Schedule",
  decision_date: "2026-08-25",
  owner: "Test Manager",
  status: "Proposed",
  rationale: null,
  approver: null,
  approval_date: null,
  delivery_impact: null,
  related_milestone_id: null,
  related_risk_id: null,
  related_change_request_id: null,
  related_requirement_id: null,
};

const CHANGE_REQUEST = {
  row_version: 11,
  change_request_id: "CR-900",
  project_id: "P-002",
  requirement_id: "REQ-900",
  change_description: "Revise the synthetic acceptance threshold",
  reason: "The reviewed test evidence requires an explicit threshold.",
  priority: "Medium",
  status: "Open",
  requested_by: "Another Requester",
  requested_date: "2026-08-25",
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

describe("governed outcomes", () => {
  it("sends the reviewed Decision version with an outcome", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      const path = String(url);
      if (path.includes("/auth/me")) return ok(PROFILE);
      if (path.includes("/outcome")) return ok({ ...DECISION, status: "Approved" });
      return ok([DECISION]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<DecisionsTab projectId="P-002" />);

    await user.click(await screen.findByText(DECISION.title));
    await user.type(
      await screen.findByLabelText("Reasoning"),
      "The reviewed evidence supports approval.",
    );
    await user.click(await screen.findByRole("button", { name: "Record outcome" }));
    expect(await screen.findByText("Choose an outcome.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Outcome"), "Approved");
    await user.click(screen.getByRole("button", { name: "Record outcome" }));
    expect(fetchMock.mock.calls.some(([url])=>String(url).includes("/outcome"))).toBe(false);
    await user.click(screen.getByRole("button",{name:"Confirm outcome"}));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/outcome"));
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        outcome: "Approved",
        row_version: 7,
      });
    });
  });

  it("sends the reviewed Change Request version with a decision", async () => {
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      const path = String(url);
      if (path.includes("/auth/me")) return ok(PROFILE);
      if (path.includes("/impact")) {
        return ok({
          estimated_schedule_impact_days: 0,
          risk_level: "Low",
          explanation: "No downstream schedule movement is calculated.",
          affected_task_ids: [],
          affected_test_case_ids: [],
          affected_milestone_ids: [],
          affected_dependency_ids: [],
          assumptions_or_limitations: [],
          source_ids: ["CR-900", "REQ-900"],
          evidence_status: "Assessed",
        });
      }
      if (path.includes("/decision")) {
        return ok({ ...CHANGE_REQUEST, status: "Approved" });
      }
      return ok([CHANGE_REQUEST]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<ChangesTab projectId="P-002" />);

    await user.click(await screen.findByText(CHANGE_REQUEST.change_description));
    await user.type(
      await screen.findByLabelText("Rationale"),
      "The reviewed evidence supports this change.",
    );
    await user.selectOptions(screen.getByLabelText("Decision"), "Approved");
    await user.click(await screen.findByRole("button", { name: "Record decision" }));
    expect(fetchMock.mock.calls.some(([url])=>String(url).includes("/decision"))).toBe(false);
    await user.click(screen.getByRole("button",{name:"Confirm decision"}));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/decision"));
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        decision: "Approved",
        row_version: 11,
      });
    });
  });
});