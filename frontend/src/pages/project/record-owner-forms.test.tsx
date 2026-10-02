import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionsTab } from "@/pages/project/decisions-tab";
import { RisksTab } from "@/pages/project/risks-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse({ permissions: ["portfolio.read", "risk.manage", "change.create"] })).user;
const PEOPLE = [{ user_id: 41, full_name: "Synthetic Reviewer", email: "reviewer@epos.example.com", workspace_role: "external_reviewer", role_label: "External Reviewer" }];
const RISK = {
  risk_id: "R-901", project_id: "P-002", risk_name: "Synthetic capacity risk", probability: 3,
  impact: 4, severity_score: 12, status: "Open", mitigation_owner: "Historical Owner",
  mitigation_status: "Not started", due_date: "2026-12-01", row_version: 7,
};

function response(body: unknown, status = 200) {
  return { ok: status < 400, status, text: async () => JSON.stringify(body) };
}

function mockApi(rejectOwner = false) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return response(PROFILE);
    if (url.includes("/people?purpose=")) return response(PEOPLE);
    if (init?.method === "PATCH" || init?.method === "POST") {
      if (rejectOwner) return response({ detail: [{ loc: ["body", "owner"], msg: "Select an active project member." }] }, 422);
      return response({ ...RISK, ...JSON.parse(String(init.body)) });
    }
    if (url.includes("/decisions") || url.includes("/change-requests")) return response([]);
    if (url.endsWith("/projects/P-002/risks")) return response([RISK]);
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

async function openRisk(): Promise<void> {
  await userEvent.click(await screen.findByRole("button", { name: `Open ${RISK.risk_id}` }));
  await screen.findByRole("option", { name: "Synthetic Reviewer · External Reviewer" });
}

describe("risk owner form", () => {
  it("saves the chosen member's name and account with the existing risk version", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RisksTab projectId="P-002" />);
    await openRisk();
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("historical");
    await userEvent.selectOptions(screen.getByLabelText("Mitigation owner"), "41");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "PATCH");
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body).toMatchObject({ mitigation_owner: "Synthetic Reviewer", mitigation_owner_user_id: 41, row_version: 7 });
      expect(body).not.toHaveProperty("owner_user_id");
    });
    expect(api.mock.calls.some(([url]) => String(url).endsWith("/people?purpose=risk"))).toBe(true);
  });

  it("preserves an untouched historical owner during an unrelated risk update", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RisksTab projectId="P-002" />);
    await openRisk();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "Mitigating");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "PATCH");
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body).toEqual({ status: "Mitigating", row_version: 7 });
    });
  });

  it("offers only the statuses the API accepts", async () => {
    vi.stubGlobal("fetch", mockApi());
    renderWithProviders(<RisksTab projectId="P-002" />);
    await openRisk();
    const options = within(screen.getByLabelText("Status")).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Open", "Mitigating", "Closed", "Accepted"]);
    expect(screen.getByLabelText("Mitigation status")).toHaveValue("Not Started");
  });

  it("requires a reason before a risk is closed and sends it with the change", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RisksTab projectId="P-002" />);
    await openRisk();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "Closed");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Record why this risk is being marked Closed.")).toBeInTheDocument();
    expect(api.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);

    await userEvent.type(screen.getByLabelText("Reason"), "The second source is qualified.");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Set the mitigation to Complete or Not Required before closing the risk.")).toBeInTheDocument();
    expect(api.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);

    await userEvent.selectOptions(screen.getByLabelText("Mitigation status"), "Not Required");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({
        status: "Closed",
        mitigation_status: "Not Required",
        rationale: "The second source is qualified.",
        row_version: 7,
      });
    });
  });

  it("clears an optional owner without restoring the historical fallback", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<RisksTab projectId="P-002" />);
    await openRisk();
    await userEvent.selectOptions(screen.getByLabelText("Mitigation owner"), "");
    expect(screen.getByLabelText("Mitigation owner")).toHaveValue("");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ mitigation_owner: null, row_version: 7 });
    });
  });
});

async function openDecision(): Promise<void> {
  await userEvent.click(await screen.findByRole("button", { name: "Record decision" }));
  await userEvent.type(screen.getByLabelText("Title"), "Synthetic review decision");
  await userEvent.type(screen.getByLabelText("Description"), "Review the synthetic qualification evidence.");
  await screen.findByRole("option", { name: "Synthetic Reviewer · External Reviewer" });
}

async function saveDecision(): Promise<void> {
  await userEvent.click(within(screen.getByRole("dialog", { name: "Record a decision" })).getByRole("button", { name: "Record decision" }));
}

describe("decision owner form", () => {
  it("creates a proposed decision using the registered member name", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    renderWithProviders(<DecisionsTab projectId="P-002" />);
    await openDecision();
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "41");
    await saveDecision();
    await waitFor(() => {
      const call = api.mock.calls.find(([, init]) => init?.method === "POST");
      const body = JSON.parse(String(call?.[1]?.body));
      expect(body).toMatchObject({ owner: "Synthetic Reviewer", project_id: "P-002", title: "Synthetic review decision" });
      expect(body).not.toHaveProperty("owner_user_id");
    });
    expect(api.mock.calls.some(([url]) => String(url).endsWith("/people?purpose=decision"))).toBe(true);
  });

  it("requires an owner and presents API owner errors without losing the draft", async () => {
    const api = mockApi(true);
    vi.stubGlobal("fetch", api);
    renderWithProviders(<DecisionsTab projectId="P-002" />);
    await openDecision();
    await saveDecision();
    expect(screen.getByLabelText("Owner")).toHaveAttribute("aria-invalid", "true");
    expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await userEvent.selectOptions(screen.getByLabelText("Owner"), "41");
    await saveDecision();
    await waitFor(() => expect(screen.getByLabelText("Owner")).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getByLabelText("Owner")).toHaveAccessibleDescription(/Select an active project member/);
    expect(screen.getByLabelText("Title")).toHaveValue("Synthetic review decision");
    expect(screen.getByLabelText("Owner")).toHaveValue("41");
  });
});