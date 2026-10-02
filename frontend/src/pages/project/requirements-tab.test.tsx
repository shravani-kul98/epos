import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequirementsTab } from "@/pages/project/requirements-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "requirement.manage"] })).user;
const PEOPLE = [{ user_id: 41, full_name: "Synthetic Reviewer", email: "reviewer@epos.example.com", workspace_role: "requirements_manager", role_label: "Requirements Manager" }];
const MATRIX = { as_of_date: "2026-09-24", project_id: "P-002", total_requirements: 0, status_counts: {}, coverage_percent: 0, rows: [] };

function response(body: unknown, status = 200) {
  return { ok: status < 400, status, text: async () => JSON.stringify(body) };
}

function mockApi() {
  return vi.fn(async (input: string, init?: RequestInit) => {
    if (input.includes("/auth/me")) return response(PROFILE);
    if (input.includes("/people?purpose=requirement")) return response(PEOPLE);
    if (init?.method === "POST" && input.endsWith("/requirements")) {
      return response({
        row_version: 1, requirement_id: "REQ-2003", project_id: "P-002",
        requirement_text: "Firmware shall log every calibration run", requirement_type: "Performance",
        priority: "High", status: "Approved", owner: "Synthetic Reviewer", last_updated_date: "2026-09-24",
      }, 201);
    }
    if (input.includes("/analytics/traceability")) return response(MATRIX);
    return response([]);
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("RequirementsTab", () => {
  it("creates a requirement with the chosen values and the registered owner's name", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<RequirementsTab projectId="P-002" />);

    await user.click(await screen.findByRole("button", { name: "New requirement" }));
    const dialog = within(screen.getByRole("dialog", { name: "New requirement" }));
    const create = dialog.getByRole("button", { name: "Create requirement" });
    expect(create).toBeDisabled();
    await user.type(dialog.getByLabelText("Requirement text"), "Firmware shall log every calibration run");
    await user.selectOptions(dialog.getByLabelText("Type"), "Performance");
    await user.selectOptions(dialog.getByLabelText("Priority"), "High");
    await user.selectOptions(dialog.getByLabelText("Status"), "Approved");
    await dialog.findByRole("option", { name: "Synthetic Reviewer · Requirements Manager" });
    await user.selectOptions(dialog.getByLabelText("Owner"), "41");
    await user.click(create);

    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        project_id: "P-002",
        requirement_text: "Firmware shall log every calibration run",
        requirement_type: "Performance",
        priority: "High",
        status: "Approved",
        owner: "Synthetic Reviewer",
      });
    });
    expect(await screen.findByText(/Requirement REQ-2003 created/)).toBeInTheDocument();
  });
});
