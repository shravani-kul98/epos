import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkTab } from "@/pages/project/work-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(
  tokenResponse({ id: 17, permissions: ["portfolio.read", "work.update"] }),
).user;

const TASK = {
  row_version: 4,
  task_id: "T-MINE",
  project_id: "P-002",
  milestone_id: "M-202",
  deliverable_id: null,
  parent_task_id: null,
  task_name: "My assigned task",
  owner: "Test Manager",
  owner_user_id: 17,
  status: "In Progress",
  planned_start_date: null,
  forecast_start_date: null,
  actual_start_date: null,
  planned_end_date: "2026-09-01",
  forecast_end_date: "2026-09-05",
  actual_end_date: null,
  forecast_start_variance_days: null,
  forecast_finish_variance_days: 4,
  actual_start_variance_days: null,
  actual_finish_variance_days: null,
  completion_percent: 40,
  is_blocked: false,
  last_updated_date: "2026-08-25",
};

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

describe("WorkTab", () => {
  beforeEach(() => {
    window.localStorage.setItem("epos.access_token", "test-token");
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("sends only progress fields when an engineer updates their assigned task", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
      const path = String(input);
      if (path.includes("/auth/me")) return ok(PROFILE);
      if (init?.method === "PATCH") return ok({ ...TASK, completion_percent: 55 });
      if (path.includes("/milestones")) return ok([]);
      if (path.includes("/scenarios/dependencies")) return ok([]);
      return ok([TASK]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<WorkTab projectId="P-002" asOfDate="2026-08-25" />);

    await user.click(await screen.findByRole("button", { name: "Open T-MINE" }));
    expect(await screen.findByLabelText("Completion")).toBeInTheDocument();
    expect(screen.queryByLabelText("Assigned to")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Forecast end date")).not.toBeInTheDocument();

    const completion = screen.getByLabelText("Completion");
    await user.clear(completion);
    await user.type(completion, "55");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        completion_percent: 55,
        row_version: 4,
      });
    });
  });
});