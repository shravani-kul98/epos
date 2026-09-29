import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskReviewActions } from "@/components/tasks/task-review-actions";
import { useAuth } from "@/lib/auth";
import { renderWithProviders, tokenResponse } from "@/test-utils";
import type { Task } from "@/types/api";

const MANAGER = JSON.parse(tokenResponse({ id: 17, permissions: ["portfolio.read", "work.update", "work.manage"] })).user;
const TASK: Task = {
  task_id: "T-REVIEW", project_id: "P-002", milestone_id: "M-202", task_name: "Bench calibration",
  owner: "Synthetic Engineer", owner_user_id: 23, status: "Complete", completion_percent: 100,
  row_version: 6, is_blocked: false, last_updated_date: "2026-09-23",
  planned_end_date: "2026-10-15", forecast_end_date: "2026-10-15", planned_start_date: null,
  forecast_start_date: null, actual_start_date: null, actual_end_date: null, deliverable_id: "D-201",
  parent_task_id: null, forecast_start_variance_days: null, forecast_finish_variance_days: 0,
  actual_start_variance_days: null, actual_finish_variance_days: null,
  review_required: true, review_status: "Pending review", reviewed_by: null, reviewed_at: null, review_note: null,
};
const HISTORY = [
  { id: 31, occurred_at: "2026-09-23T10:00:00", action: "completed", actor_name: "Synthetic Engineer", note: "Bench log attached to the release folder.", changes: [] },
  { id: 30, occurred_at: "2026-09-20T10:00:00", action: "updated", actor_name: "Synthetic Engineer", note: "Half the channels are done.", changes: [] },
];
const DELIVERABLES = [{
  deliverable_id: "D-201", project_id: "P-002", work_package_id: "WP-20", deliverable_name: "Calibrated bench",
  description: "Bench ready for release testing.", owner: null, accountable_owner: null, status: "In Progress",
  priority: "High", acceptance_criteria: "Signed bench log for every channel.", completion_evidence: null,
}];

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

function mockApi() {
  return vi.fn(async (input: string, init?: RequestInit) => {
    if (input.includes("/auth/me")) return ok(MANAGER);
    if (input.endsWith("/tasks/T-REVIEW/progress")) return ok(HISTORY);
    if (input.endsWith("/projects/P-002/deliverables")) return ok(DELIVERABLES);
    if (init?.method === "POST" && input.endsWith("/tasks/T-REVIEW/review")) {
      return ok({ ...TASK, review_status: "Accepted", reviewed_by: "Test Manager", row_version: 7 });
    }
    return ok([]);
  });
}

function reviewBody(api: ReturnType<typeof mockApi>): unknown {
  const call = api.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith("/review"));
  return call ? JSON.parse(String(call[1]?.body)) : undefined;
}

function SignedInAs(): JSX.Element {
  const { user } = useAuth();
  return <p>{user ? `Signed in as ${user.full_name}` : "Signing in"}</p>;
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("TaskReviewActions", () => {
  it("shows the completion note and criteria, and will not return work without a note", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<TaskReviewActions task={TASK} />);

    await user.click(await screen.findByRole("button", { name: "Return for rework" }));
    const dialog = within(screen.getByRole("dialog", { name: "Return for rework?" }));
    expect(await dialog.findByText("Bench log attached to the release folder.")).toBeInTheDocument();
    expect(dialog.queryByText("Half the channels are done.")).not.toBeInTheDocument();
    expect(await dialog.findByText("Signed bench log for every channel.")).toBeInTheDocument();

    const confirm = dialog.getByRole("button", { name: "Confirm return" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("What needs to change"), "   ");
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("What needs to change"), "Attach the calibration certificate.");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(reviewBody(api)).toEqual({
      decision: "return", note: "Attach the calibration certificate.", row_version: 6,
    }));
  });

  it("accepts completed work with the reviewed version", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<TaskReviewActions task={TASK} />);

    await user.click(await screen.findByRole("button", { name: "Accept" }));
    const dialog = within(screen.getByRole("dialog", { name: "Accept this work?" }));
    await user.click(dialog.getByRole("button", { name: "Confirm acceptance" }));

    await waitFor(() => expect(reviewBody(api)).toEqual({ decision: "accept", row_version: 6 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("offers no review controls to a role that cannot manage work", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ok(input.includes("/auth/me") ? { ...MANAGER, permissions: ["portfolio.read", "work.update"] } : [])));
    renderWithProviders(<><SignedInAs /><TaskReviewActions task={TASK} /></>);

    expect(await screen.findByText("Signed in as Test Manager")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return for rework" })).not.toBeInTheDocument();
  });
});
