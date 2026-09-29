import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActionAssignee } from "@/components/actions/action-assignee";
import { renderWithProviders, tokenResponse } from "@/test-utils";
import type { Action } from "@/types/api";

const MANAGER = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "action.manage", "work.manage"] })).user;
const ENGINEER = JSON.parse(tokenResponse({ id: 23, permissions: ["portfolio.read", "work.update"] })).user;

const ACTION: Action = {
  row_version: 3,
  action_id: "A-2001",
  project_id: "P-002",
  action_description: "Confirm the bench schedule",
  owner: "Legacy Owner",
  owner_user_id: null,
  due_date: "2026-10-01",
  status: "Open",
  priority: "High",
  source_reference: null,
};

const PEOPLE = [
  { user_id: 23, full_name: "Test Engineer", email: "engineer@epos.example.com", workspace_role: "engineer", role_label: "Engineer" },
];

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

function mockApi(user: unknown) {
  return vi.fn(async (input: string, init?: RequestInit) => {
    if (input.includes("/auth/me")) return ok(user);
    if (input.endsWith("/projects/P-002/assignees")) return ok(PEOPLE);
    if (init?.method === "PATCH") return ok({ ...ACTION, owner: "Test Engineer", owner_user_id: 23, row_version: 4 });
    return ok({});
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "cookie");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("ActionAssignee", () => {
  it("links the action to a member's account with its stored version", async () => {
    const api = mockApi(MANAGER);
    vi.stubGlobal("fetch", api);
    const onAssigned = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<ActionAssignee action={ACTION} onAssigned={onAssigned} />);

    await screen.findByRole("option", { name: "Test Engineer · Engineer" });
    await user.selectOptions(screen.getByLabelText("Assigned account"), "23");
    await user.click(screen.getByRole("button", { name: "Save assignment" }));

    await waitFor(() => expect(onAssigned).toHaveBeenCalledWith(expect.objectContaining({ owner_user_id: 23 })));
    const patch = api.mock.calls.find(([url, init]) => String(url).endsWith("/actions/A-2001") && init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ owner_user_id: 23, row_version: 3 });
  });

  it("is not offered to a role that cannot manage actions and work", async () => {
    const api = mockApi(ENGINEER);
    vi.stubGlobal("fetch", api);
    renderWithProviders(<ActionAssignee action={ACTION} />);

    // The session is read only after the profile has loaded.
    await waitFor(() => expect(api.mock.calls.some(([url]) => String(url).includes("/auth/session"))).toBe(true));
    expect(screen.queryByLabelText("Assigned account")).not.toBeInTheDocument();
    expect(api.mock.calls.some(([url]) => String(url).includes("/assignees"))).toBe(false);
  });
});
