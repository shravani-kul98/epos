import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StatusUpdateAction } from "@/pages/project/overview-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const EDITOR = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "project.update"] })).user;
const READER = JSON.parse(tokenResponse({ permissions: ["portfolio.read"] })).user;
const PROJECT = { project_id: "P-002", project_name: "Synthetic programme", row_version: 4, status_update_date: "2026-08-01" };
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

function mockApi(profile: unknown) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return ok(profile);
    if (url.endsWith("/projects/P-002/status-update") && init?.method === "POST") {
      return ok({ ...PROJECT, row_version: 5, status_update_date: "2026-09-23" });
    }
    if (url.endsWith("/projects/P-002")) return ok(PROJECT);
    throw new Error(`Unexpected request: ${url}`);
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("Recording a status update", () => {
  it("confirms the current record version and leaves the date to the server", async () => {
    const api = mockApi(EDITOR);
    vi.stubGlobal("fetch", api);
    renderWithProviders(<StatusUpdateAction projectId="P-002" />);

    await userEvent.click(await screen.findByRole("button", { name: "Record status update" }));

    await waitFor(() => {
      const post = api.mock.calls.find(([, init]) => init?.method === "POST");
      expect(post?.[0]).toContain("/projects/P-002/status-update");
      expect(JSON.parse(String(post?.[1]?.body))).toEqual({ row_version: 4 });
    });
  });

  it("is not offered to someone who cannot update the project", async () => {
    const api = mockApi(READER);
    vi.stubGlobal("fetch", api);
    renderWithProviders(<StatusUpdateAction projectId="P-002" />);

    await waitFor(() => expect(api).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Record status update" })).not.toBeInTheDocument();
  });
});
