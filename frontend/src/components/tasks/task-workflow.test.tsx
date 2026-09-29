import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CreateWorkDrawer } from "@/components/tasks/create-work-drawer";
import { TaskEditor } from "@/components/tasks/task-editor";
import { MyWorkPage } from "@/pages/my-work";
import { createTestQueryClient, renderWithProviders, tokenResponse } from "@/test-utils";
import type { Task } from "@/types/api";

const MANAGER = JSON.parse(tokenResponse({ id: 17, permissions: ["portfolio.read", "work.update", "work.manage", "project_members.manage"] })).user;
const ENGINEER = { ...MANAGER, id: 23, full_name: "Synthetic Engineer", role: "engineer", permissions: ["portfolio.read", "work.update"] };
const PEOPLE = [
  { user_id: 23, full_name: "Synthetic Engineer", email: "one@test.example.com", workspace_role: "engineer", role_label: "Engineer" },
  { user_id: 24, full_name: "Synthetic Engineer", email: "two@test.example.com", workspace_role: "engineer", role_label: "Engineer" },
];
const TASK: Task = {
  task_id: "T-WORKFLOW", project_id: "P-002", milestone_id: "M-202", task_name: "Synthetic validation task",
  owner: "Synthetic Engineer", owner_user_id: 23, status: "In Progress", completion_percent: 40,
  row_version: 4, is_blocked: false, last_updated_date: "2026-08-25",
  planned_end_date: "2026-10-15", forecast_end_date: "2026-10-15", planned_start_date: null,
  forecast_start_date: null, actual_start_date: null, actual_end_date: null, deliverable_id: null,
  parent_task_id: null, forecast_start_variance_days: null, forecast_finish_variance_days: 0,
  actual_start_variance_days: null, actual_finish_variance_days: null,
  review_required: false, review_status: null, reviewed_by: null, reviewed_at: null, review_note: null,
};
const MILESTONES = [{ milestone_id: "M-202", project_id: "P-002", milestone_name: "Validation checkpoint" }];
const PORTFOLIO = { as_of_date: "2026-08-25", projects: [{ project_id: "P-002", project_name: "Synthetic programme" }] };
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

beforeEach(() => { window.localStorage.setItem("epos.access_token", "test-token"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Account-based task workflow", () => {
  it("creates a task assigned to the selected account, even when names repeat", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(MANAGER);
      if (input.includes("/assignees")) return ok(PEOPLE);
      if (input.includes("/milestones")) return ok(MILESTONES);
      if (init?.method === "POST") return ok({ ...TASK, status: "Not Started", completion_percent: 0 });
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const created = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<CreateWorkDrawer projectId="P-002" kind="task" onClose={vi.fn()} onNeedMilestone={vi.fn()} onCreated={created} />);
    await user.type(screen.getByLabelText("Task name"), "Synthetic validation task");
    await screen.findByRole("option", { name: "Validation checkpoint" });
    await user.selectOptions(screen.getByLabelText("Milestone"), "M-202");
    await screen.findByRole("option", { name: /two@test.example.com/ });
    await user.selectOptions(screen.getByLabelText("Assigned to"), "24");
    fireEvent.change(screen.getByLabelText("Planned due date"), { target: { value: "2026-10-15" } });
    await user.click(screen.getByRole("button", { name: "Create task" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      project_id: "P-002", milestone_id: "M-202", task_name: "Synthetic validation task", owner_user_id: 24,
      planned_end_date: "2026-10-15", forecast_end_date: "2026-10-15", status: "Not Started", completion_percent: 0,
    });
  });

  it("offers a first milestone instead of a dead-end task form", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ok(input.includes("/auth/me") ? MANAGER : [])));
    const addMilestone = vi.fn();
    renderWithProviders(<CreateWorkDrawer projectId="P-002" kind="task" onClose={vi.fn()} onNeedMilestone={addMilestone} onCreated={vi.fn()} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Add the first milestone" }));
    expect(addMilestone).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Create task" })).toBeDisabled();
  });

  it("reassigns by account ID without submitting an owner name", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(MANAGER);
      if (input.includes("/assignees")) return ok(PEOPLE);
      if (init?.method === "PATCH") return ok({ ...TASK, owner_user_id: 24 });
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const saved = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<TaskEditor task={TASK} onClose={vi.fn()} onSaved={saved} />);
    await screen.findByRole("option", { name: /two@test.example.com/ });
    await user.selectOptions(screen.getByLabelText("Assigned to"), "24");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ owner_user_id: 24, row_version: 4 });
  });

  it("retains the draft when another user has already changed the task", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(MANAGER);
      if (input.includes("/assignees")) return ok(PEOPLE);
      if (init?.method === "PATCH") return { ok: false, status: 409, text: async () => JSON.stringify({ detail: "This record changed after it was loaded." }) };
      return ok([TASK]);
    }));
    const close = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<TaskEditor task={TASK} onClose={close} />);
    const name = await screen.findByLabelText("Task name");
    await user.clear(name);
    await user.type(name, "Reviewed synthetic task");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed after it was loaded");
    expect(name).toHaveValue("Reviewed synthetic task");
    expect(close).not.toHaveBeenCalled();
  });

  it("lets an engineer complete work and updates cached manager task views", async () => {
    let current = TASK;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ENGINEER);
      if (input.includes("/analytics/portfolio")) return ok(PORTFOLIO);
      if (init?.method === "POST" && input.endsWith("/complete")) {
        current = { ...TASK, status: "Complete", completion_percent: 100, is_blocked: false, row_version: 5 };
        return ok(current);
      }
      if (input.includes("/actions")) return ok([]);
      return ok([current]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = createTestQueryClient();
    queryClient.setQueryData(["tasks", "P-002"], [TASK]);
    const user = userEvent.setup();
    renderWithProviders(<MyWorkPage />, { queryClient });
    await user.click(await screen.findByRole("button", { name: "Mark complete" }));
    await user.click(screen.getByRole("button", { name: "Confirm completion" }));
    expect(await screen.findByText("Complete")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark complete" })).not.toBeInTheDocument();
    expect(await screen.findByText("Completion recorded")).toBeInTheDocument();
    expect(queryClient.getQueryData<Task[]>(["tasks", "P-002"])?.[0]?.status).toBe("Complete");
    expect(queryClient.getQueryData<Task[]>(["task-register", "all"])?.[0]?.status).toBe("Complete");
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ row_version: 4 });
  });

  it("lets an engineer report partial progress in their own words", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ENGINEER);
      if (init?.method === "PATCH") return ok({ ...TASK, completion_percent: 30, row_version: 5 });
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const saved = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<TaskEditor task={TASK} onClose={vi.fn()} onSaved={saved} />);
    const completion = await screen.findByLabelText("Completion");
    await user.clear(completion);
    await user.type(completion, "30");
    await user.type(screen.getByLabelText("Progress note"), "Fixture wiring done; calibration runs next.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      completion_percent: 30, progress_note: "Fixture wiring done; calibration runs next.", row_version: 4,
    });
  });

  it("saves a note on its own as a progress report", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ENGINEER);
      if (init?.method === "PATCH") return ok({ ...TASK, row_version: 5 });
      return ok([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<TaskEditor task={TASK} onClose={vi.fn()} />);
    const save = await screen.findByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Progress note"), "Still waiting for the supplier fixture.");
    await user.click(save);
    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ progress_note: "Still waiting for the supplier fixture.", row_version: 4 });
    });
  });

  it("sends a completion note with the completion", async () => {
    let current = TASK;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ENGINEER);
      if (input.includes("/analytics/portfolio")) return ok(PORTFOLIO);
      if (init?.method === "POST" && input.endsWith("/complete")) {
        current = { ...TASK, status: "Complete", completion_percent: 100, row_version: 5 };
        return ok(current);
      }
      if (input.includes("/actions")) return ok([]);
      return ok([current]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<MyWorkPage />);
    await user.click(await screen.findByRole("button", { name: "Mark complete" }));
    await user.type(screen.getByLabelText("Completion note"), "Calibrated and verified on bench 3.");
    await user.click(screen.getByRole("button", { name: "Confirm completion" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toEqual({ row_version: 4, progress_note: "Calibrated and verified on bench 3." });
    });
  });

  it("shows the task history in the reporters' own words", async () => {
    const history = [
      { id: 12, occurred_at: "2026-08-25T09:30:00", action: "updated", actor_name: "Synthetic Engineer", note: "Fixture wiring done; calibration runs next.",
        changes: [{ field: "completion_percent", label: "Completion percent", before: 10, after: 30 }] },
      { id: 11, occurred_at: "2026-08-20T08:00:00", action: "created", actor_name: "Test Manager", note: null, changes: [] },
    ];
    vi.stubGlobal("fetch", vi.fn(async (input: string) => {
      if (input.includes("/auth/me")) return ok(ENGINEER);
      if (input.endsWith("/tasks/T-WORKFLOW/progress")) return ok(history);
      return ok([]);
    }));
    renderWithProviders(<TaskEditor task={TASK} onClose={vi.fn()} />);
    expect(await screen.findByText("Fixture wiring done; calibration runs next.")).toBeInTheDocument();
    expect(screen.getByText("Completion percent: 10% → 30%")).toBeInTheDocument();
    expect(screen.getByText(/Updated by Synthetic Engineer/)).toBeInTheDocument();
    expect(screen.getByText(/Created by Test Manager/)).toBeInTheDocument();
  });
});
