import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PeoplePage } from "@/pages/people";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const ADMIN = JSON.parse(tokenResponse({ id: 1, role: "administrator", role_label: "Administrator", full_name: "Synthetic Admin", permissions: ["portfolio.read", "user.manage"] })).user;
const PERSON = JSON.parse(tokenResponse({ id: 23, email: "engineer@test.example.com", full_name: "Synthetic Engineer", role: "engineer", role_label: "Engineer", permissions: ["portfolio.read", "work.update"] })).user;
const ROLES = [
  { role: "engineer", label: "Engineer", permissions: ["portfolio.read", "work.update"] },
  { role: "project_manager", label: "Project Manager", permissions: ["portfolio.read", "work.manage"] },
  { role: "administrator", label: "Administrator", permissions: ["user.manage"] },
];
const INVITED = {
  id: 7, email: "new.person@test.example.com", role: "engineer", role_label: "Engineer", created_by: "Synthetic Admin",
  created_at: "2026-09-24T08:00:00Z", expires_at: "2026-10-01T08:00:00Z", status: "Pending",
};
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });
beforeEach(() => { window.localStorage.setItem("epos.access_token", "cookie"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Team and access administration", () => {
  it("offers role dropdowns and changes a selected person's role only after confirmation", async () => {
    let person = PERSON;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ADMIN);
      if (input.endsWith("/roles")) return ok(ROLES);
      if (input.endsWith("/admin/invitations")) return ok([]);
      if (init?.method === "PATCH") { person = { ...PERSON, role: "project_manager", role_label: "Project Manager" }; return ok(person); }
      return ok([ADMIN, person]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<PeoplePage />);
    const select = await screen.findByRole("combobox", { name: /Role for Synthetic Engineer/ });
    await user.selectOptions(select, "project_manager");
    await user.click(screen.getByRole("button", { name: "Save role" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm role change" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Role saved: Project Manager");
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(patch?.[0]).toContain("/admin/users/23/role");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ role: "project_manager" });
  });

  it("protects the signed-in administrator's own account", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ok(
      input.includes("/auth/me") ? ADMIN : input.endsWith("/roles") ? ROLES : input.endsWith("/admin/invitations") ? [] : [ADMIN],
    )));
    renderWithProviders(<PeoplePage />);
    expect(await screen.findByRole("combobox", { name: /Role for Synthetic Admin/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Disable account" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset password" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "End sessions" })).toBeDisabled();
  });

  it("shows a temporary password once after a confirmed reset", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ADMIN);
      if (input.endsWith("/roles")) return ok(ROLES);
      if (input.endsWith("/admin/invitations")) return ok([]);
      if (init?.method === "POST") return ok({ user_id: 23, temporary_password: "Temporary-Pass-8842" });
      return ok([ADMIN, PERSON]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<PeoplePage />);
    const buttons = await screen.findAllByRole("button", { name: "Reset password" });
    const available = buttons.filter((button) => !(button as HTMLButtonElement).disabled);
    expect(available).toHaveLength(1);

    await user.click(available[0]!);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm password reset" }));

    expect(await screen.findByText("Temporary-Pass-8842")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toContain("/admin/users/23/reset-password");
    await user.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByText("Temporary-Pass-8842")).not.toBeInTheDocument());
  });

  it("does not request admin user data for a PMO account", async () => {
    const pmo = { ...ADMIN, role: "pmo_analyst", permissions: ["portfolio.read", "work.manage", "project_members.manage"] };
    const fetchMock = vi.fn(async (input: string) => ok(input.includes("/auth/me") ? pmo : {}));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<PeoplePage />);
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => input.endsWith("/auth/session"))).toBe(true));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => input.includes("/admin/"))).toBe(false);
  });

  it("ends another person's sessions only after confirmation", async () => {
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ADMIN);
      if (input.endsWith("/roles")) return ok(ROLES);
      if (input.endsWith("/admin/invitations")) return ok([]);
      if (init?.method === "POST") return { ok: true, status: 204, text: async () => "" };
      return ok([ADMIN, PERSON]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<PeoplePage />);
    const buttons = await screen.findAllByRole("button", { name: "End sessions" });
    const available = buttons.filter((button) => !(button as HTMLButtonElement).disabled);
    expect(available).toHaveLength(1);

    await user.click(available[0]!);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm end sessions" }));

    expect(await screen.findByRole("heading", { name: "Sessions ended" })).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toContain("/admin/users/23/revoke-sessions");
  });
});

describe("Invitations", () => {
  it("shows an invitation link once, copies it and lists the pending invitation", async () => {
    let invitations: unknown[] = [];
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ADMIN);
      if (input.endsWith("/roles")) return ok(ROLES);
      if (input.endsWith("/admin/invitations") && init?.method === "POST") {
        invitations = [INVITED];
        return { ok: true, status: 201, text: async () => JSON.stringify({ invitation: INVITED, code: "Invite-Code-1234567890" }) };
      }
      if (input.endsWith("/admin/invitations")) return ok(invitations);
      return ok([ADMIN, PERSON]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    renderWithProviders(<PeoplePage />);

    const roleSelect = await screen.findByLabelText("Role");
    await waitFor(() => expect(within(roleSelect).getByRole("option", { name: "Engineer" })).toBeInTheDocument());
    await user.type(screen.getByLabelText("Email address"), "new.person@test.example.com");
    await user.selectOptions(roleSelect, "engineer");
    await user.click(screen.getByRole("button", { name: "Invite" }));

    const link = `${window.location.origin}/register?invite=Invite-Code-1234567890&email=new.person%40test.example.com`;
    expect(await screen.findByText(link)).toBeInTheDocument();
    expect(screen.getByText(/expires in 7 days/)).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ email: "new.person@test.example.com", role: "engineer" });

    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(copy).toHaveBeenCalledWith(link);
    expect(await screen.findByRole("button", { name: "Withdraw the invitation for new.person@test.example.com" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText(link)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Invite-Code-1234567890");
    copy.mockRestore();
  });

  it("withdraws a pending invitation", async () => {
    let invitation = INVITED;
    const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
      if (input.includes("/auth/me")) return ok(ADMIN);
      if (input.endsWith("/roles")) return ok(ROLES);
      if (input.endsWith("/admin/invitations/7/revoke") && init?.method === "POST") {
        invitation = { ...INVITED, status: "Revoked" };
        return ok(invitation);
      }
      if (input.endsWith("/admin/invitations")) return ok([invitation]);
      return ok([ADMIN, PERSON]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithProviders(<PeoplePage />);

    await user.click(await screen.findByRole("button", { name: "Withdraw the invitation for new.person@test.example.com" }));

    expect(await screen.findByText("Revoked")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Withdraw the invitation/ })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) => input.endsWith("/admin/invitations/7/revoke") && init?.method === "POST")).toBe(true);
  });
});
