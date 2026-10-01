import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InboxPage } from "@/pages/inbox";
import { renderWithProviders, tokenResponse } from "@/test-utils";
import type { InboxNotification } from "@/types/api";

const ENGINEER = JSON.parse(tokenResponse({ id: 23, permissions: ["portfolio.read", "work.update"] })).user;

const NOTIFICATIONS: InboxNotification[] = [
  {
    id: 2, kind: "review_returned", title: "Returned task Bench calibration for rework",
    detail: "Attach the calibration log.", project_id: "P-002", entity_type: "Task", entity_id: "T-2001",
    actor_name: "Test Manager", created_at: "2026-09-24T09:30:00Z", read_at: null,
  },
  {
    id: 1, kind: "action_assigned", title: "You were assigned action A-2001",
    detail: null, project_id: "P-002", entity_type: "Action", entity_id: "A-2001",
    actor_name: "Test Manager", created_at: "2026-09-23T08:00:00Z", read_at: "2026-09-23T09:00:00Z",
  },
];

function ok(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
}

function mockApi() {
  return vi.fn(async (input: string, init?: RequestInit) => {
    if (input.includes("/auth/me")) return ok(ENGINEER);
    if (init?.method === "POST" && input.endsWith("/notifications/read-all")) return ok({ unread: 0 });
    if (init?.method === "POST" && input.endsWith("/read")) return ok({ ...NOTIFICATIONS[0], read_at: "2026-09-24T10:00:00Z" });
    if (input.includes("/notifications")) return ok(NOTIFICATIONS);
    return ok([]);
  });
}

beforeEach(() => {
  window.localStorage.setItem("epos.access_token", "test-token");
});

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("InboxPage", () => {
  it("lists notifications with links to their records and marks unread ones", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<InboxPage />);

    const returned = await screen.findByRole("link", { name: "Returned task Bench calibration for rework" });
    expect(returned).toHaveAttribute("href", "/projects/P-002?tab=work&task=T-2001");
    expect(returned).toHaveClass("font-semibold");
    expect(screen.getByRole("link", { name: "You were assigned action A-2001" })).toHaveAttribute("href", "/projects/P-002?tab=team");
    const list = within(screen.getByRole("list", { name: "Notifications" }));
    expect(list.getAllByText("Unread")).toHaveLength(1);
    expect(list.getByText("Attach the calibration log.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Awaiting your review" })).not.toBeInTheDocument();
  });

  it("marks everything read in one request", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await screen.findByRole("link", { name: "Returned task Bench calibration for rework" });
    const markAll = screen.getByRole("button", { name: "Mark all as read" });
    await waitFor(() => expect(markAll).toBeEnabled());
    await user.click(markAll);

    await waitFor(() => {
      expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/notifications/read-all") && init?.method === "POST")).toBe(true);
    });
  });

  it("marks a notification read when its record is opened", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<InboxPage />);

    await user.click(await screen.findByRole("link", { name: "Returned task Bench calibration for rework" }));

    await waitFor(() => {
      expect(api.mock.calls.some(([url, init]) => String(url).endsWith("/notifications/2/read") && init?.method === "POST")).toBe(true);
    });
  });
});
