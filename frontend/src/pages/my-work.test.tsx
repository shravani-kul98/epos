import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MyWorkPage } from "@/pages/my-work";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ id: 17 })).user;

function response(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

describe("MyWorkPage", () => {
  beforeEach(() => {
    window.localStorage.setItem("epos.access_token", "test-token");
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("shows only tasks assigned to the signed-in user identity", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: string) => {
        const path = String(input);
        if (path.includes("/auth/me")) return response(PROFILE);
        if (path.includes("/analytics/portfolio")) {
          return response({
            as_of_date: "2026-08-25",
            projects: [{ project_id: "P-002", project_name: "Synthetic Delivery" }],
          });
        }
        if (path.includes("/actions")) return response([]);
        return response([
          {
            task_id: "T-MINE",
            project_id: "P-002",
            task_name: "My assigned task",
            owner_user_id: 17,
            status: "In Progress",
            is_blocked: false,
            completion_percent: 40,
            forecast_end_date: "2026-09-01",
          },
          {
            task_id: "T-OTHER",
            project_id: "P-002",
            task_name: "Another person's task",
            owner_user_id: 23,
            status: "In Progress",
            is_blocked: false,
            completion_percent: 10,
            forecast_end_date: "2026-09-02",
          },
        ]);
      }),
    );

    renderWithProviders(<MyWorkPage />);

    expect(await screen.findByText("My assigned task")).toBeInTheDocument();
    expect(screen.queryByText("Another person's task")).not.toBeInTheDocument();
  });

  it("lists only the user's own actions and needs a reason to move one", async () => {
    const worker = JSON.parse(tokenResponse({ id: 17, permissions: ["portfolio.read", "work.update"] })).user;
    const mine = {
      action_id: "A-MINE", project_id: "P-002", action_description: "Confirm supplier capacity",
      owner: "Test Manager", owner_user_id: 17, due_date: "2026-09-30", status: "Open",
      priority: "High", source_reference: null, row_version: 2,
    };
    const other = { ...mine, action_id: "A-OTHER", action_description: "Another person's action", owner: "Synthetic Engineer", owner_user_id: 23 };
    const api = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return response(worker);
      if (input.includes("/analytics/portfolio")) {
        return response({ as_of_date: "2026-09-24", projects: [{ project_id: "P-002", project_name: "Synthetic Delivery" }] });
      }
      if (init?.method === "POST" && input.endsWith("/actions/A-MINE/transition")) {
        return response({ ...mine, status: "In Progress", row_version: 3 });
      }
      if (input.includes("/actions")) return response([mine, other]);
      return response([]);
    });
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<MyWorkPage />);

    const start = await screen.findByRole("button", { name: "Start A-MINE" });
    expect(screen.getByText("Confirm supplier capacity")).toBeInTheDocument();
    expect(screen.queryByText("Another person's action")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start A-OTHER" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete A-MINE" })).not.toBeInTheDocument();

    await user.click(start);
    const dialog = within(screen.getByRole("dialog", { name: "Start this action" }));
    const confirm = dialog.getByRole("button", { name: "Confirm" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("Reason"), "Supplier call booked for Monday.");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => {
      const call = api.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith("/transition"));
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        target_status: "In Progress",
        rationale: "Supplier call booked for Monday.",
        row_version: 2,
      });
    });
  });
});