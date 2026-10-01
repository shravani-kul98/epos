import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getCsrfToken, setCsrfToken } from "@/lib/api";
import { RolePermissionsPage } from "@/pages/role-permissions";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse()).user;
const NEW_PASSWORD = "A-fresh-passphrase-2026";
const SESSIONS = [
  {
    id: "session-current", created_at: "2026-09-24T08:00:00Z", last_seen_at: "2026-09-24T09:30:00Z", expires_at: "2026-09-24T20:00:00Z",
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", current: true,
  },
  {
    id: "session-laptop", created_at: "2026-09-24T07:00:00Z", last_seen_at: "2026-09-24T07:45:00Z", expires_at: "2026-09-24T19:00:00Z",
    user_agent: "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", current: false,
  },
];
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

function mockApi(changeStatus = 204, changeDetail = "") {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/change-password")) {
      return changeStatus === 204
        ? { ok: true, status: 204, text: async () => "" }
        : { ok: false, status: changeStatus, text: async () => JSON.stringify({ detail: changeDetail }) };
    }
    if (url.endsWith("/auth/login") && init?.method === "POST") {
      return ok({ ...JSON.parse(tokenResponse()), csrf_token: "csrf-after-change" });
    }
    if (url.endsWith("/auth/sessions")) return ok(SESSIONS);
    return ok(PROFILE);
  });
}

async function fill(current: string, next: string, confirm = next): Promise<void> {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Current password"), current);
  await user.type(screen.getByLabelText("New password"), next);
  await user.type(screen.getByLabelText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "cookie");
});

afterEach(() => {
  window.localStorage.clear();
  setCsrfToken(null);
  vi.unstubAllGlobals();
});

describe("Changing your own password", () => {
  it("changes the password, then signs straight back in with the new one", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RolePermissionsPage />);

    await fill("old-password-123", NEW_PASSWORD);

    expect(await screen.findByRole("status")).toHaveTextContent("Password changed.");
    const change = api.mock.calls.find(([url]) => url.endsWith("/auth/change-password"));
    expect(JSON.parse(String(change?.[1]?.body))).toEqual({ current_password: "old-password-123", new_password: NEW_PASSWORD });
    const login = api.mock.calls.find(([url]) => url.endsWith("/auth/login"));
    expect(JSON.parse(String(login?.[1]?.body))).toEqual({ email: PROFILE.email, password: NEW_PASSWORD });
    await waitFor(() => expect(getCsrfToken()).toBe("csrf-after-change"));
    expect(window.localStorage.getItem("epos.access_token")).toBe("cookie");
  });

  it("shows the service's reason when the current password is wrong", async () => {
    vi.stubGlobal("fetch", mockApi(403, "Your current password is not correct."));
    renderWithProviders(<RolePermissionsPage />);

    await fill("not-my-password", NEW_PASSWORD);

    expect(await screen.findByRole("alert")).toHaveTextContent("Your current password is not correct.");
    expect(screen.getByLabelText("Current password")).toHaveValue("not-my-password");
  });

  it("checks the confirmation before sending anything", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RolePermissionsPage />);

    await fill("old-password-123", NEW_PASSWORD, `${NEW_PASSWORD}-typo`);

    expect(await screen.findByRole("alert")).toHaveTextContent("Both new passwords must match.");
    expect(api.mock.calls.some(([url]) => url.endsWith("/auth/change-password"))).toBe(false);
  });
});

describe("Active sessions", () => {
  it("lists the account's sessions and signs out another device", async () => {
    let sessions = SESSIONS;
    const api = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/sessions/session-laptop/revoke") && init?.method === "POST") {
        sessions = SESSIONS.filter((session) => session.current);
        return { ok: true, status: 204, text: async () => "" };
      }
      if (url.endsWith("/auth/sessions")) return ok(sessions);
      return ok(PROFILE);
    });
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<RolePermissionsPage />);

    expect(await screen.findByText("Firefox on Linux")).toBeInTheDocument();
    expect(screen.getByText("Chrome on Windows")).toBeInTheDocument();
    expect(screen.getByText("This device")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Sign out Chrome on Windows/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Sign out Firefox on Linux/ }));

    expect(await screen.findByRole("status")).toHaveTextContent("Firefox on Linux was signed out.");
    await waitFor(() => expect(screen.queryByText("Firefox on Linux")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Sign out all other sessions" })).toBeDisabled();
    const revoke = api.mock.calls.find(([url]) => url.endsWith("/revoke"));
    expect(revoke?.[0]).toContain("/auth/sessions/session-laptop/revoke");
    expect(revoke?.[1]?.method).toBe("POST");
  });
});
