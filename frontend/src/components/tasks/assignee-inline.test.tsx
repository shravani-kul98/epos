import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssigneeField } from "@/components/tasks/assignee-field";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const MANAGER = JSON.parse(tokenResponse({ id: 1, permissions: ["work.manage", "project_members.manage"] })).user;
const PERSON = { user_id: 23, full_name: "Synthetic Engineer", email: "engineer@test.example.com", workspace_role: "engineer", role_label: "Engineer" };
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });
function Form(): JSX.Element {
  const [assignee, setAssignee] = useState<number | null>(null);
  return <form><input aria-label="Task draft" defaultValue="Keep these instructions" /><AssigneeField projectId="P-002" value={assignee} onChange={setAssignee} /><output aria-label="Chosen account">{assignee}</output></form>;
}
beforeEach(() => { window.localStorage.setItem("epos.access_token", "test-token"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Inline member addition", () => {
  it("grants access only after confirmation and preserves the task draft", async () => {
    let added = false;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(MANAGER);
      if (input.includes("/member-candidates")) return ok(added ? [] : [PERSON]);
      if (init?.method === "POST") { added = true; return ok({ ...PERSON, project_role: "Contributor", is_active: true }); }
      return ok(added ? [PERSON] : []);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<Form />);
    await user.click(await screen.findByRole("button", { name: "Add another person…" }));
    await screen.findByRole("option", { name: /engineer@test.example.com/ });
    await user.selectOptions(screen.getByLabelText("Person to add"), "23");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(screen.getByText(/Adding them grants project access/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to project and select" }));
    await waitFor(() => expect(screen.getByLabelText("Chosen account")).toHaveTextContent("23"));
    expect(screen.getByLabelText("Task draft")).toHaveValue("Keep these instructions");
    expect(screen.getByLabelText("Assigned to")).toHaveValue("23");
    const write = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(write?.[1]?.body))).toEqual({ user_id: 23, project_role: "Contributor" });
  });
  it("never exposes a workspace picker to an engineering lead", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ok(input.includes("/auth/me") ? { ...MANAGER, permissions: ["work.manage"] } : [])));
    renderWithProviders(<Form />);
    await screen.findByText(/Ask a Project Manager or PMO Analyst/);
    expect(screen.queryByRole("button", { name: "Add another person…" })).not.toBeInTheDocument();
  });
});
