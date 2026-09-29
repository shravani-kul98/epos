import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangesTab } from "@/pages/project/changes-tab";
import { GatesTab } from "@/pages/project/gates-tab";
import { IssuesTab } from "@/pages/project/issues-tab";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PEOPLE = [{ user_id: 41, full_name: "Synthetic Lead", email: "lead@epos.example.com", workspace_role: "engineering_lead", role_label: "Engineering Lead" }];

const ISSUE = {
  row_version: 3, issue_id: "ISS-P-002-001", project_id: "P-002", title: "Fixture unavailable",
  description: "The synthetic validation fixture is unavailable.", severity: "High", owner: null, status: "Open",
  raised_date: "2026-09-20", target_resolution_date: null, resolution_summary: null, resolved_by: null,
  resolved_at: null, source_reference: null,
};

const GATE = {
  row_version: 5, gate_id: "G-P-002-001", project_id: "P-002", milestone_id: null, gate_name: "Synthetic design review",
  sequence: 1, planned_review_date: "2026-10-15", actual_review_date: null, owner: "Test Manager", status: "Preparing",
  review_cycle: 1, result: null, applicable_baseline: null,
};

const CRITERION = {
  row_version: 2, criterion_id: "GC-P-002-001", gate_id: GATE.gate_id, project_id: "P-002", criterion_type: "Exit",
  criterion_name: "Verification evidence accepted", description: "The synthetic verification record is reviewed.",
  is_mandatory: true, evidence_required: true, status: "Not Assessed", evidence_reference: null,
  assessment_rationale: null, assessed_by: null, assessed_at: null,
};

const READINESS = {
  gate_id: GATE.gate_id, project_id: "P-002", state: "Not Ready", percentage: 0,
  complete_criterion_ids: [], incomplete_criterion_ids: [CRITERION.criterion_id], blockers: [], warnings: [],
  evidence_references: [], latest_review_id: null, latest_review_outcome: null,
  calculated_at: "2026-09-24T09:00:00Z", methodology_version: "1", applicable_baseline: null,
};

function ok(body: unknown, status = 200) {
  return { ok: status < 400, status, text: async () => JSON.stringify(body) };
}

function profile(permissions: string[]) {
  return JSON.parse(tokenResponse({ permissions: ["portfolio.read", ...permissions] })).user;
}

/** The JSON body of the first request with this method whose URL ends as given. */
function sent(api: { mock: { calls: unknown[][] } }, method: string, ending: string): unknown {
  const call = api.mock.calls.find(entry => {
    const [url, init] = entry as [string, RequestInit | undefined];
    return init?.method === method && String(url).endsWith(ending);
  }) as [string, RequestInit] | undefined;
  return call ? JSON.parse(String(call[1].body)) : undefined;
}

beforeEach(() => { window.localStorage.setItem("epos.access_token", "test-token"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("issue register", () => {
  function mockApi() {
    return vi.fn(async (input: string, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return ok(profile(["issue.manage"]));
      if (url.includes("/people?purpose=issue")) return ok(PEOPLE);
      if (init?.method === "POST" && url.endsWith("/transition")) return ok({ ...ISSUE, status: "Resolved", row_version: 4 });
      if (init?.method === "POST" && url.endsWith("/issues")) return ok({ ...ISSUE, ...JSON.parse(String(init.body)), issue_id: "ISS-P-002-002" }, 201);
      if (url.includes("/issues")) return ok([ISSUE]);
      return ok([]);
    });
  }

  it("raises an issue without inventing its reference", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<IssuesTab projectId="P-002" />);

    await user.click(await screen.findByRole("button", { name: "Raise issue" }));
    const dialog = within(screen.getByRole("dialog", { name: "Raise issue" }));
    const submit = dialog.getByRole("button", { name: "Raise issue" });
    expect(submit).toBeDisabled();
    await user.type(dialog.getByLabelText("Title"), "Supplier sample late");
    await user.type(dialog.getByLabelText("What happened"), "The supplier sample did not arrive for qualification.");
    await user.selectOptions(dialog.getByLabelText("Severity"), "Critical");
    await user.click(submit);

    await waitFor(() => expect(sent(api, "POST", "/issues")).toBeDefined());
    const body = sent(api, "POST", "/issues") as Record<string, unknown>;
    expect(body).not.toHaveProperty("issue_id");
    expect(body).not.toHaveProperty("status");
    expect(body).toMatchObject({ project_id: "P-002", title: "Supplier sample late", severity: "Critical", owner: null });
    expect(body.raised_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(await screen.findByText(/Issue ISS-P-002-002 raised/)).toBeInTheDocument();
  });

  it("resolves an issue with its resolution summary and version", async () => {
    const api = mockApi();
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<IssuesTab projectId="P-002" />);

    await user.click(await screen.findByRole("button", { name: `Open ${ISSUE.issue_id}` }));
    const dialog = within(screen.getByRole("dialog", { name: ISSUE.title }));
    expect(dialog.getByRole("button", { name: "Start work" })).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Resolve" }));
    const confirm = dialog.getByRole("button", { name: "Confirm resolve" });
    expect(confirm).toBeDisabled();
    await user.type(dialog.getByLabelText("Resolution summary"), "A spare fixture was borrowed from the lab.");
    await user.click(confirm);

    await waitFor(() => expect(sent(api, "POST", "/transition")).toEqual({
      target_status: "Resolved", rationale: "A spare fixture was borrowed from the lab.", row_version: 3,
    }));
  });
});

describe("gate criteria", () => {
  it("requires named evidence before a criterion that needs it can be met", async () => {
    const api = vi.fn(async (input: string, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return ok(profile(["work.manage", "work.update"]));
      if (init?.method === "POST" && url.endsWith("/assessment")) return ok({ ...CRITERION, status: "Met", row_version: 3 });
      if (url.endsWith("/readiness")) return ok(READINESS);
      if (url.endsWith("/criteria")) return ok([CRITERION]);
      if (url.endsWith("/reviews")) return ok([]);
      if (url.endsWith("/projects/P-002/gates")) return ok([GATE]);
      return ok([]);
    });
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<GatesTab projectId="P-002" />);

    await user.click(await screen.findByRole("button", { name: `Open ${GATE.gate_id}` }));
    const dialog = within(screen.getByRole("dialog", { name: GATE.gate_name }));
    expect(await dialog.findByRole("button", { name: "Mark ready for review" })).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: `Assess ${CRITERION.criterion_id}` }));
    await user.type(dialog.getByLabelText("Reasoning"), "The verification record was reviewed.");
    const save = dialog.getByRole("button", { name: "Save assessment" });
    expect(save).toBeDisabled();
    await user.type(dialog.getByLabelText("Evidence reference"), "EV-SYNTHETIC-7");
    await user.click(save);

    await waitFor(() => expect(sent(api, "POST", "/assessment")).toEqual({
      target_status: "Met", rationale: "The verification record was reviewed.", row_version: 2, evidence_reference: "EV-SYNTHETIC-7",
    }));
  });
});

describe("change requests", () => {
  it("raises a change against a chosen requirement, leaving the reference to the API", async () => {
    const api = vi.fn(async (input: string, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) return ok(profile(["change.create"]));
      if (url.endsWith("/projects/P-002/requirements")) return ok([{ requirement_id: "REQ-2001", project_id: "P-002", requirement_text: "Boot within two seconds", requirement_type: "Performance", priority: "High", status: "Approved", owner: null, last_updated_date: null }]);
      if (init?.method === "POST" && url.endsWith("/change-requests")) return ok({ ...JSON.parse(String(init.body)), change_request_id: "CR-P-002-001", status: "Raised", requested_by: "Test Manager", row_version: 1 }, 201);
      return ok([]);
    });
    vi.stubGlobal("fetch", api);
    const user = userEvent.setup();
    renderWithProviders(<ChangesTab projectId="P-002" />);

    await user.click(await screen.findByRole("button", { name: "Raise change request" }));
    const dialog = within(screen.getByRole("dialog", { name: "Raise change request" }));
    await dialog.findByRole("option", { name: /REQ-2001/ });
    await user.selectOptions(dialog.getByLabelText("Requirement"), "REQ-2001");
    await user.type(dialog.getByLabelText("Proposed change"), "Boot within one and a half seconds");
    await user.type(dialog.getByLabelText("Reason"), "Customer review feedback");
    await user.click(dialog.getByRole("button", { name: "Raise change request" }));

    await waitFor(() => expect(sent(api, "POST", "/change-requests")).toBeDefined());
    const body = sent(api, "POST", "/change-requests") as Record<string, unknown>;
    expect(body).not.toHaveProperty("change_request_id");
    expect(body).toMatchObject({ project_id: "P-002", requirement_id: "REQ-2001", priority: "Medium", reason: "Customer review feedback" });
    expect(await screen.findByText(/Change request CR-P-002-001 raised/)).toBeInTheDocument();
  });
});
