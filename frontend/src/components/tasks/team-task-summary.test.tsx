import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamTaskSummary } from "@/components/tasks/team-task-summary";
import { renderWithProviders } from "@/test-utils";

const TASKS = [
  { task_id: "T-ACTIVE", project_id: "P-002", task_name: "Open synthetic work", owner: "Synthetic Engineer", owner_user_id: 23, status: "In Progress", completion_percent: 40, is_blocked: false, last_updated_date: "2026-09-21" },
  { task_id: "T-DONE", project_id: "P-002", task_name: "Finished synthetic work", owner: "Synthetic Engineer", owner_user_id: 23, status: "Complete", completion_percent: 100, is_blocked: false, last_updated_date: "2026-09-22" },
  { task_id: "T-LEGACY", project_id: "P-002", task_name: "Work without account", owner: "Legacy label", owner_user_id: null, status: "Not Started", completion_percent: 0, is_blocked: false, last_updated_date: null },
];
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });
afterEach(() => { vi.unstubAllGlobals(); window.localStorage.clear(); });

describe("Manager task visibility", () => {
  it("shows saved completed tasks and links directly to their project task editor", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(TASKS)));
    const user = userEvent.setup();
    renderWithProviders(<TeamTaskSummary />);
    await screen.findByRole("button", { name: "Completed tasks 1" });
    await user.selectOptions(screen.getByLabelText("Task status"), "completed");
    const table = within(screen.getByRole("region", { name: "Team tasks table" }));
    expect(table.getByRole("link", { name: "Finished synthetic work" })).toHaveAttribute("href", "/projects/P-002?tab=work&task=T-DONE");
    expect(table.getByText("100%")).toBeInTheDocument();
    expect(table.queryByText("Open synthetic work")).not.toBeInTheDocument();
  });

  it("counts work reported complete but awaiting review apart from accepted work", async () => {
    const pending = { ...TASKS[1], task_id: "T-PENDING", task_name: "Reported synthetic work", review_required: true, review_status: "Pending review" };
    vi.stubGlobal("fetch", vi.fn(async () => ok([...TASKS, pending])));
    const user = userEvent.setup();
    renderWithProviders(<TeamTaskSummary />);
    await screen.findByRole("button", { name: "Completed tasks 1" });
    expect(screen.getByRole("button", { name: "Awaiting review 1" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Task status"), "review");
    const table = within(screen.getByRole("region", { name: "Team tasks table" }));
    expect(table.getByRole("link", { name: "Reported synthetic work" })).toBeInTheDocument();
    expect(table.getByText("Awaiting review")).toBeInTheDocument();
    expect(table.queryByText("Finished synthetic work")).not.toBeInTheDocument();
  });

  it("re-reads team tasks when the manager refreshes after another user's update", async () => {
    let rows = [TASKS[0]];
    vi.stubGlobal("fetch", vi.fn(async () => ok(rows)));
    const user = userEvent.setup();
    renderWithProviders(<TeamTaskSummary projectId="P-002" />);
    await screen.findByRole("button", { name: "Completed tasks 0" });
    rows = [TASKS[1]];
    await user.click(screen.getByRole("button", { name: "Refresh team tasks" }));
    expect(await screen.findByRole("button", { name: "Completed tasks 1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Finished synthetic work" })).toBeInTheDocument();
  });

  it("shows an error instead of inventing zero totals when the task request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, text: async () => "{}" })));
    renderWithProviders(<TeamTaskSummary />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Completed tasks 0" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Completed tasks —" })).toBeInTheDocument();
  });
});
