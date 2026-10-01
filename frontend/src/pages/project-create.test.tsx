import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectCreatePage } from "@/pages/project-create";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const PROFILE = JSON.parse(tokenResponse()).user;
const OPTIONS = {
  domains: ["Sustainability", "Engineering"],
  managers: [
    { user_id: 21, full_name: "Alex Morgan", email: "alex@epos.example.com", role_label: "Project Manager", workspace_role: "project_manager" },
    { user_id: 22, full_name: "Alex Morgan", email: "alex.pmo@epos.example.com", role_label: "PMO Analyst", workspace_role: "pmo_analyst" },
  ],
};

function response(body: unknown, status = 200) {
  return { ok: status < 400, status, text: async () => JSON.stringify(body) };
}

function mockApi(options = OPTIONS, createStatus = 201) {
  return vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/me")) return response(PROFILE);
    if (url.endsWith("/projects/options")) return response(options);
    if (url.endsWith("/projects") && init?.method === "POST") {
      return response(createStatus === 201 ? JSON.parse(String(init.body)) : { detail: "exists" }, createStatus);
    }
    throw new Error(`Unexpected request: ${url}`);
  });
}

async function fillBasics(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Project name"), "Supplier Decarbonisation Programme");
  await screen.findByRole("option", { name: /alex@epos.example.com/ });
  await user.selectOptions(screen.getByLabelText("Domain"), "domain:Sustainability");
  await user.selectOptions(screen.getByLabelText("Project manager"), "21");
}

async function advanceToReview(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await user.type(screen.getByLabelText("Start date"), "2026-09-01");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await user.click(screen.getByRole("button", { name: "Continue" }));
}

describe("ProjectCreatePage", () => {
  beforeEach(() => {
    window.localStorage.setItem("epos.access_token", "test-token");
    vi.stubGlobal("fetch", mockApi());
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("guides the user through steps rather than one long form", () => {
    renderWithProviders(<ProjectCreatePage />);

    expect(screen.getByText("Project basics")).toBeInTheDocument();
    expect(screen.getByText("Review and create")).toBeInTheDocument();
    // Timeline fields belong to a later step and must not appear yet.
    expect(screen.queryByLabelText("Start date")).not.toBeInTheDocument();
  });

  it("suggests a reference so the user never invents a database key", async () => {
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Project name"), "Supplier Decarbonisation Programme");
    expect((screen.getByLabelText("Project reference") as HTMLInputElement).value).toMatch(/^SD-\d{3}$/);
  });

  it("blocks progress and preserves entries when required fields are missing", async () => {
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Project name"), "Supplier Decarbonisation Programme");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Domain is required.")).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveValue("Supplier Decarbonisation Programme");
  });

  it("rejects a target date that falls before the start date", async () => {
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await user.type(screen.getByLabelText("Start date"), "2026-09-01");
    await user.type(screen.getByLabelText("Target completion"), "2026-08-01");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(
      await screen.findByText("The target date cannot fall before the start date."),
    ).toBeInTheDocument();
  });

  it("shows a review summary before anything is created", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Start date"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByText("Supplier Decarbonisation Programme")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create project" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    expect(screen.getByText(/Creating the project grants the selected manager project access/)).toBeInTheDocument();
  });

  it("reports a duplicate reference without losing the draft", async () => {
    vi.stubGlobal("fetch", mockApi(OPTIONS, 409));
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();

    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Start date"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("A project already uses that identifier.");
    });
    expect(screen.getByText("Supplier Decarbonisation Programme")).toBeInTheDocument();
  });

  it("submits the selected manager ID and full name, distinguishing duplicate names by email", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await fillBasics(user);
    await user.selectOptions(screen.getByLabelText("Project manager"), "22");
    expect(screen.getByText(/Creating the project grants this person project access/)).toBeInTheDocument();
    await advanceToReview(user);
    expect(screen.getByText("Alex Morgan · alex.pmo@epos.example.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        project_manager: "Alex Morgan", project_manager_user_id: 22, domain: "Sustainability",
      });
    });
  });

  it("offers only authorized domains and an explicit new-domain input", async () => {
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await screen.findByRole("option", { name: "Engineering" });
    expect(screen.queryByLabelText("New domain")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Domain"), "new");
    await user.type(screen.getByLabelText("New domain"), "Synthetic reliability");
    await user.selectOptions(screen.getByLabelText("Domain"), "domain:Engineering");
    expect(screen.queryByLabelText("New domain")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Domain")).toHaveValue("domain:Engineering");
  });

  it("creates with an explicitly entered domain when there are no existing domains", async () => {
    const fetchMock = mockApi({ ...OPTIONS, domains: [] });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await screen.findByRole("option", { name: /alex@epos.example.com/ });
    await user.type(screen.getByLabelText("Project name"), "Synthetic pilot");
    await user.selectOptions(screen.getByLabelText("Project manager"), "21");
    await user.selectOptions(screen.getByLabelText("Domain"), "new");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByLabelText("New domain")).toHaveAttribute("aria-invalid", "true");
    await user.type(screen.getByLabelText("New domain"), "Synthetic reliability");
    await advanceToReview(user);
    await user.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ domain: "Synthetic reliability", project_manager_user_id: 21 });
    });
  });

  it("preserves entered details and retries a failed options request", async () => {
    let fail = true;
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) =>
      url.endsWith("/projects/options") && fail ? response({}, 503) : api(url, init),
    ));
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Project name"), "Synthetic pilot");
    expect(await screen.findByRole("alert")).toHaveTextContent("EPOS could not complete the request");
    expect(screen.getByLabelText("Project manager")).toBeDisabled();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry project options" }));
    await screen.findByRole("option", { name: /alex@epos.example.com/ });
    expect(screen.getByLabelText("Project name")).toHaveValue("Synthetic pilot");
  });

  it("explains an empty manager pool without allowing a free-text manager", async () => {
    vi.stubGlobal("fetch", mockApi({ ...OPTIONS, managers: [] }));
    renderWithProviders(<ProjectCreatePage />);
    expect(await screen.findByText(/No active project managers are available/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Project manager" })).toHaveValue("");
    expect(screen.queryByRole("textbox", { name: "Project manager" })).not.toBeInTheDocument();
  });

  it("retains the selected manager when refreshed options remove that account and blocks progress", async () => {
    let options = OPTIONS;
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) =>
      url.endsWith("/projects/options") ? Promise.resolve(response(options)) : api(url, init),
    ));
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await fillBasics(user);
    options = { ...OPTIONS, managers: [OPTIONS.managers[1]!] };
    await user.click(screen.getByRole("button", { name: "Refresh project options" }));
    expect(await screen.findByRole("option", { name: "Alex Morgan — no longer available" })).toBeDisabled();
    expect(screen.getByLabelText("Project manager")).toHaveValue("21");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByLabelText("Project manager")).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByLabelText("Start date")).not.toBeInTheDocument();
  });

  it("creates the first milestone and risk with statuses the API accepts", async () => {
    const created: Array<{ url: string; body: Record<string, unknown> }> = [];
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST" && (url.endsWith("/milestones") || url.endsWith("/risks"))) {
        const body = JSON.parse(String(init.body));
        created.push({ url, body });
        return response(body, 201);
      }
      return api(url, init);
    }));
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Start date"), "2026-09-01");
    await user.type(screen.getByLabelText("First milestone"), "Design freeze");
    await user.type(screen.getByLabelText("Milestone target date"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("First risk"), "Supplier data quality is incomplete");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(created).toHaveLength(2));
    expect(created.find((item) => item.url.endsWith("/milestones"))?.body).toMatchObject({ status: "Not Started" });
    expect(created.find((item) => item.url.endsWith("/risks"))?.body).toMatchObject({ status: "Open", mitigation_status: "Not Started" });
    expect(created.find((item) => item.url.endsWith("/milestones"))?.body).not.toHaveProperty("milestone_id");
    expect(created.find((item) => item.url.endsWith("/risks"))?.body).not.toHaveProperty("risk_id");
  });

  it("retries only the step that failed once the project exists", async () => {
    const posts: string[] = [];
    let milestoneFails = true;
    const api = mockApi();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") posts.push(url);
      if (init?.method === "POST" && url.endsWith("/milestones")) {
        if (milestoneFails) return response({ detail: "Temporarily unavailable" }, 503);
        return response(JSON.parse(String(init.body)), 201);
      }
      return api(url, init);
    }));
    renderWithProviders(<ProjectCreatePage />);
    const user = userEvent.setup();
    await fillBasics(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(screen.getByLabelText("Start date"), "2026-09-01");
    await user.type(screen.getByLabelText("First milestone"), "Design freeze");
    await user.type(screen.getByLabelText("Milestone target date"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("The project was created.")).toBeInTheDocument();
    milestoneFails = false;
    await user.click(screen.getByRole("button", { name: "Try the remaining steps again" }));

    await waitFor(() => expect(posts.filter(url => url.endsWith("/milestones"))).toHaveLength(2));
    expect(posts.filter(url => url.endsWith("/projects"))).toHaveLength(1);
  });

  it("does not fetch project options before login", () => {
    window.localStorage.clear();
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProjectCreatePage />);
    expect(screen.getByLabelText("Project manager")).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not fetch project options without project.create permission", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return response({ ...PROFILE, permissions: ["portfolio.read"] });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProjectCreatePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith("/projects/options"))).toBe(false);
    expect(screen.getByLabelText("Project manager")).toBeDisabled();
  });
});
