import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test-utils";
import { WhatChanged } from "@/pages/project/what-changed";

function delta(overrides: Record<string, unknown> = {}): unknown {
  return {
    project_id: "P-002",
    project_name: "Supplier Data Migration",
    since: "2026-08-18T00:00:00Z",
    generated_at: "2026-08-25T00:00:00Z",
    total_changes: 2,
    has_history: true,
    earliest_record_at: "2026-01-05T00:00:00Z",
    groups: [
      {
        key: "delivery",
        label: "Delivery",
        added: 0,
        updated: 1,
        withdrawn: 0,
        entries: [
          {
            entity_type: "milestone",
            entity_id: "M-202",
            change_type: "updated",
            headline: "Supplier qualification was updated and now stands at At Risk.",
            status: "At Risk",
            occurred_at: "2026-08-24T09:00:00Z",
            actor_name: "Alex Morgan",
          },
        ],
      },
      {
        key: "risks",
        label: "Risks",
        added: 1,
        updated: 0,
        withdrawn: 0,
        entries: [
          {
            entity_type: "risk",
            entity_id: "R-900",
            change_type: "added",
            headline: "Supplier tooling capacity is unconfirmed was added at Open.",
            status: "Open",
            occurred_at: "2026-08-23T09:00:00Z",
            actor_name: null,
          },
        ],
      },
    ],
    ...overrides,
  };
}

function mockApi(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what changed", () => {
  it("groups the movement and names who made it", async () => {
    vi.stubGlobal("fetch", mockApi(delta()));
    renderWithProviders(<WhatChanged projectId="P-002" />);

    expect(
      await screen.findByText("Supplier qualification was updated and now stands at At Risk."),
    ).toBeInTheDocument();
    expect(screen.getByText("Delivery")).toBeInTheDocument();
    expect(screen.getByText("Risks")).toBeInTheDocument();
    expect(screen.getByText(/Alex Morgan/)).toBeInTheDocument();
  });

  it("counts each kind of change so the reader can skim", async () => {
    vi.stubGlobal("fetch", mockApi(delta()));
    renderWithProviders(<WhatChanged projectId="P-002" />);

    expect(await screen.findByText("1 updated")).toBeInTheDocument();
    expect(screen.getByText("1 added")).toBeInTheDocument();
  });

  it("says there is no earlier state rather than implying nothing happened", async () => {
    vi.stubGlobal("fetch", mockApi(delta({ has_history: false, total_changes: 0, groups: [] })));
    renderWithProviders(<WhatChanged projectId="P-002" />);

    expect(
      await screen.findByText("No earlier project snapshot is available yet"),
    ).toBeInTheDocument();
  });

  it("distinguishes a quiet window from a missing history", async () => {
    vi.stubGlobal("fetch", mockApi(delta({ total_changes: 0, groups: [] })));
    renderWithProviders(<WhatChanged projectId="P-002" />);

    expect(await screen.findByText("Nothing changed in this window")).toBeInTheDocument();
  });

  it("asks the API for the window the reader chose", async () => {
    const fetchMock = mockApi(delta());
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<WhatChanged projectId="P-002" />);
    await screen.findByText("Delivery");

    await userEvent.click(screen.getByRole("button", { name: "30 days" }));

    await waitFor(() => {
      const requested = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(requested.some((url) => url.includes("/projects/P-002/delta?days=30"))).toBe(true);
    });
  });

  it("offers a retry when the history cannot be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => JSON.stringify({ detail: "Something went wrong." }),
      }),
    );
    renderWithProviders(<WhatChanged projectId="P-002" />);

    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
