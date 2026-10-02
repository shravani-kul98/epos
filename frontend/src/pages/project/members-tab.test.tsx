import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MembersTab } from "@/pages/project/members-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "project_members.manage"] })).user;
const PERSON = { user_id: 23, full_name: "Synthetic Engineer", email: "engineer@test.example.com", workspace_role: "engineer", role_label: "Engineer" };
const MEMBER = { ...PERSON, is_active: true, project_role: "Contributor", created_at: "2026-09-22T00:00:00Z" };
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

beforeEach(() => { window.localStorage.setItem("epos.access_token", "test-token"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Project members", () => {
  it("adds a selected registered account rather than a typed name", async () => {
    let added = false;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(PROFILE);
      if (input.includes("/member-candidates")) return ok(added ? [] : [PERSON]);
      if (init?.method === "POST") { added = true; return ok(MEMBER); }
      return ok(added ? [MEMBER] : []);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<MembersTab projectId="P-002" />);
    await user.click(await screen.findByRole("button", { name: "Add member" }));
    await screen.findByRole("option", { name: /engineer@test.example.com/ });
    await user.selectOptions(screen.getByLabelText("Person"), "23");
    await user.click(screen.getByRole("button", { name: "Add to project" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Project member added");
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit responsibility" })).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ user_id: 23, project_role: "Contributor" });
  });

  it("shows a removal refusal without removing the member locally", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(PROFILE);
      if (init?.method === "DELETE") return { ok: false, status: 409, text: async () => JSON.stringify({ detail: "Reassign or complete this member's open tasks first." }) };
      return ok([MEMBER]);
    }));
    const user = userEvent.setup();
    renderWithProviders(<MembersTab projectId="P-002" />);
    await user.click(await screen.findByRole("button", { name: "Remove access" }));
    await user.click(screen.getByRole("button", { name: "Confirm removal" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Reassign or complete");
    expect(screen.getByRole("button", { name: "Confirm removal" })).toBeInTheDocument();
  });
});
