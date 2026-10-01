import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const EMPTY_PORTFOLIO = {
  as_of_date: "2026-08-25", project_count: 0,
  health_bands: { red: 0, amber: 0, green: 0 }, confidence_bands: { low: 0, medium: 0, high: 0 },
  alert_severities: { critical: 0, high: 0, medium: 0, low: 0 }, project_phases: {}, project_domains: {}, projects: [], top_alerts: [],
};
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Password change after an administrator reset", () => {
  it("shows only the password change until the temporary password is replaced", async () => {
    window.localStorage.setItem("epos.access_token", "cookie");
    const flagged = JSON.parse(tokenResponse({ password_change_required: true })).user;
    const posts: Array<{ path: string; body: unknown }> = [];
    const reads: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
      const url = String(input);
      const path = url.replace(/^.*\/api\/v1/, "");
      if (init?.method === "POST") posts.push({ path, body: init.body ? JSON.parse(String(init.body)) : null });
      else reads.push(path);
      if (path === "/auth/me") return ok(flagged);
      if (path === "/auth/session") return ok({ csrf_token: "csrf", expires_at: "2099-01-01T00:00:00Z", session_expires_at: "2099-01-01T00:00:00Z" });
      if (path === "/auth/change-password") return { ok: true, status: 204, text: async () => "" };
      if (path === "/auth/login") return { ok: true, status: 200, text: async () => tokenResponse() };
      if (path.startsWith("/analytics/portfolio")) return ok(EMPTY_PORTFOLIO);
      return ok([]);
    }));
    const user = userEvent.setup();
    renderWithProviders(<App />, { route: "/my-work" });

    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    expect(reads.every(path => path.startsWith("/auth/"))).toBe(true);

    await user.type(screen.getByLabelText("Temporary password"), "temporary-pass-123");
    await user.type(screen.getByLabelText("New password"), "a-chosen-passphrase-91");
    await user.type(screen.getByLabelText("Confirm new password"), "a-chosen-passphrase-92");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Both new passwords must match.");
    expect(posts).toHaveLength(0);

    await user.clear(screen.getByLabelText("Confirm new password"));
    await user.type(screen.getByLabelText("Confirm new password"), "a-chosen-passphrase-91");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => expect(screen.queryByRole("heading", { name: "Choose a new password" })).not.toBeInTheDocument());
    expect(posts.map(post => post.path)).toEqual(["/auth/change-password", "/auth/login"]);
    expect(posts[0]?.body).toEqual({ current_password: "temporary-pass-123", new_password: "a-chosen-passphrase-91" });
    expect(posts[1]?.body).toMatchObject({ password: "a-chosen-passphrase-91" });
  });

  it("keeps the ordinary workspace for an account without a temporary password", async () => {
    window.localStorage.setItem("epos.access_token", "cookie");
    vi.stubGlobal("fetch", vi.fn(async (input: string) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return ok(JSON.parse(tokenResponse()).user);
      if (url.includes("/analytics/portfolio")) return ok(EMPTY_PORTFOLIO);
      return ok([]);
    }));
    renderWithProviders(<App />, { route: "/" });
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose a new password" })).not.toBeInTheDocument();
  });
});
