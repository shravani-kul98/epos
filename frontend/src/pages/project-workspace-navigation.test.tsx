import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectWorkspacePage } from "@/pages/project-workspace";

const state = vi.hoisted(() => ({
  permissions: [] as string[],
  assessment: undefined as { is_assessed: boolean; reason: string; source_ids: string[] } | undefined,
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ can: (permission: string) => state.permissions.includes(permission) }) }));
vi.mock("@/pages/project/overview-tab", () => ({ OverviewTab: () => <p>Overview content</p> }));
vi.mock("@/pages/project/work-tab", () => ({ WorkTab: ({ projectId, asOfDate }: { projectId: string; asOfDate: string }) => <p>Delivery content {projectId} {asOfDate}</p> }));
vi.mock("@/pages/project/members-tab", () => ({ MembersTab: ({ projectId }: { projectId: string }) => <p>Members content {projectId}</p> }));
vi.mock("@/pages/project/team-tab", () => ({ TeamTab: ({ projectId }: { projectId: string }) => <p>Team content {projectId}</p> }));
vi.mock("@/pages/project/risks-tab", () => ({ RisksTab: ({ projectId }: { projectId: string }) => <p>Risks content {projectId}</p> }));
vi.mock("@/pages/project/issues-tab", () => ({ IssuesTab: ({ projectId }: { projectId: string }) => <p>Issues content {projectId}</p> }));
vi.mock("@/pages/project/assumptions-tab", () => ({ AssumptionsTab: ({ projectId }: { projectId: string }) => <p>Assumptions content {projectId}</p> }));
vi.mock("@/pages/project/changes-tab", () => ({ ChangesTab: ({ projectId }: { projectId: string }) => <p>Changes content {projectId}</p> }));
vi.mock("@/pages/project/decisions-tab", () => ({ DecisionsTab: ({ projectId }: { projectId: string }) => <p>Decisions content {projectId}</p> }));
vi.mock("@/pages/project/meetings-tab", () => ({ MeetingsTab: ({ projectId }: { projectId: string }) => <p>Meetings content {projectId}</p> }));
vi.mock("@/pages/project/requirements-tab", () => ({ RequirementsTab: ({ projectId }: { projectId: string }) => <p>Requirements content {projectId}</p> }));
vi.mock("@/pages/project/gates-tab", () => ({ GatesTab: ({ projectId }: { projectId: string }) => <p>Gates content {projectId}</p> }));
vi.mock("@/pages/project/activity-tab", () => ({ ActivityTab: ({ projectId }: { projectId: string }) => <p>Activity content {projectId}</p> }));
vi.mock("@/components/tasks/team-task-summary", () => ({ TeamTaskSummary: ({ projectId }: { projectId: string }) => <p>Team task summary {projectId}</p> }));
vi.mock("@/lib/queries", () => ({
  useProjectDashboard: () => ({
    isLoading: false, isError: false,
    data: {
      project: { project_id: "P-001", project_name: "Navigation fixture", domain: "Engineering", project_phase: "Planning", project_manager: "Test Manager", forecast_end_date: "2026-09-30" },
      health: { score: 0, band: "Green", as_of_date: "2026-08-25" },
      confidence: { score: 0, band: "Low" },
      assessment: state.assessment,
    },
  }),
}));

beforeEach(() => { state.permissions = []; state.assessment = undefined; });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

function Location(): JSX.Element {
  const location = useLocation();
  return <>
    <output aria-label="Current route">{location.pathname}{location.search}</output>
    <Link to="/projects/P-001?tab=gates&focus=evidence">Open gates deep link</Link>
  </>;
}

function renderNavigation(route: string): void {
  vi.stubGlobal("fetch", vi.fn());
  render(<MemoryRouter initialEntries={[route]}><Routes><Route path="/projects/:projectId" element={<ProjectWorkspacePage />} /></Routes><Location /></MemoryRouter>);
}

describe("Grouped project navigation", () => {
  it("preserves the project and unrelated query parameters when switching sections", async () => {
    renderNavigation("/projects/P-001?tab=overview&focus=records&as_of=2026-08-25");
    const user = userEvent.setup();
    const categories = screen.getByRole("group", { name: "Project categories" });
    expect(within(categories).getAllByRole("button").map(button => button.textContent)).toEqual(["Overview", "Delivery", "Controls", "Evidence"]);
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    await user.click(within(categories).getByRole("button", { name: "Delivery" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/projects/P-001?tab=work&focus=records&as_of=2026-08-25");
    expect(screen.getByRole("tabpanel", { name: "Delivery plan" })).toHaveTextContent("Delivery content P-001 2026-08-25");
    await user.click(screen.getByRole("tab", { name: "Capacity & actions" }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent("/projects/P-001?tab=team&focus=records&as_of=2026-08-25");
    await user.click(within(categories).getByRole("button", { name: "Delivery" }));
    expect(screen.getByRole("tab", { name: "Capacity & actions" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tablist")).toHaveLength(1);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    for (const tab of screen.getAllByRole("tab")) {
      expect(document.getElementById(tab.getAttribute("aria-controls")!)).toBeInTheDocument();
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  it("groups every mobile option and keeps it connected to desktop state without dropping filters", async () => {
    state.permissions = ["project_members.manage"];
    renderNavigation("/projects/P-001?tab=overview&focus=records");
    const select = screen.getByRole("combobox", { name: "Project section" });
    const expected = {
      Overview: ["overview"],
      Delivery: ["work", "members", "team"],
      Controls: ["risks", "issues", "assumptions", "changes", "decisions", "meetings"],
      Evidence: ["requirements", "gates", "activity"],
    };
    for (const [group, values] of Object.entries(expected)) {
      expect(within(within(select).getByRole("group", { name: group })).getAllByRole("option").map(option => option.getAttribute("value"))).toEqual(values);
    }
    expect(within(select).getAllByRole("option")).toHaveLength(13);
    await userEvent.setup().selectOptions(select, "activity");
    expect(screen.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("tab", { name: "Audit trail" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Audit trail" })).toHaveTextContent("Activity content P-001");
    expect(screen.getByLabelText("Current route")).toHaveTextContent("tab=activity&focus=records");
  });

  it.each([
    ["overview", "Overview", "Overview", "Overview content"],
    ["work", "Delivery", "Delivery plan", "Delivery content P-001"],
    ["members", "Delivery", "Team members", "Members content P-001"],
    ["team", "Delivery", "Capacity & actions", "Team content P-001"],
    ["risks", "Controls", "Risks", "Risks content P-001"],
    ["issues", "Controls", "Issues", "Issues content P-001"],
    ["assumptions", "Controls", "Assumptions", "Assumptions content P-001"],
    ["changes", "Controls", "Change requests", "Changes content P-001"],
    ["decisions", "Controls", "Decisions", "Decisions content P-001"],
    ["meetings", "Controls", "Meetings", "Meetings content P-001"],
    ["requirements", "Evidence", "Requirements", "Requirements content P-001"],
    ["gates", "Evidence", "Gates", "Gates content P-001"],
    ["activity", "Evidence", "Audit trail", "Activity content P-001"],
  ])("opens the %s deep link in its group with existing panel wiring", (tab, group, label, content) => {
    if (tab === "members") state.permissions = ["project_members.manage"];
    renderNavigation(`/projects/P-001?tab=${tab}&focus=records`);
    expect(screen.getByRole("button", { name: group })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: label })).toHaveTextContent(content);
    expect(screen.getAllByRole("tablist")).toHaveLength(1);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires member-management permission but retains every read-only section", () => {
    renderNavigation("/projects/P-001?tab=members&focus=records");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("option", { name: "Team members" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(12);
    expect(screen.getByLabelText("Current route")).toHaveTextContent("tab=members&focus=records");
  });

  it("supports keyboard category selection and roving tabs after a group switch", async () => {
    renderNavigation("/projects/P-001?tab=work");
    const user = userEvent.setup();
    screen.getByRole("tab", { name: "Delivery plan" }).focus();
    await user.keyboard("{ArrowRight}{Enter}");
    expect(screen.getByRole("tab", { name: "Capacity & actions" })).toHaveAttribute("aria-selected", "true");
    screen.getByRole("button", { name: "Controls" }).focus();
    await user.keyboard("{Enter}");
    const risks = screen.getByRole("tab", { name: "Risks" });
    expect(risks).toHaveAttribute("tabindex", "0");
    risks.focus();
    await user.keyboard("{End}{Enter}");
    expect(screen.getByRole("tabpanel", { name: "Meetings" })).toHaveTextContent("Meetings content P-001");
    expect(screen.getByRole("tab", { name: "Meetings" })).toHaveFocus();
  });

  it("follows an in-app deep link without keeping a stale category", async () => {
    renderNavigation("/projects/P-001?tab=risks");
    await userEvent.setup().click(screen.getByRole("link", { name: "Open gates deep link" }));
    expect(screen.getByRole("button", { name: "Evidence" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("tabpanel", { name: "Gates" })).toHaveTextContent("Gates content P-001");
    expect(screen.getByLabelText("Current route")).toHaveTextContent("tab=gates&focus=evidence");
  });

  it("keeps the overview team summary permission-gated", () => {
    state.permissions = ["work.manage"];
    renderNavigation("/projects/P-001?tab=overview");
    expect(screen.getByText("Team task summary P-001")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Team members" })).not.toBeInTheDocument();
  });

  it("retains the overview fallback for an unknown section", () => {
    renderNavigation("/projects/P-001?tab=unknown");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Overview" })).toHaveTextContent("Overview content");
  });

  it("replaces numeric header badges with the API's unassessed reason", () => {
    state.assessment = { is_assessed: false, reason: "No delivery evidence has been recorded.", source_ids: ["P-001"] };
    renderNavigation("/projects/P-001?tab=overview");
    expect(screen.getByText("Not yet assessed")).toHaveClass("bg-muted-tint");
    expect(screen.getByText(state.assessment.reason)).toBeInTheDocument();
    expect(screen.queryByText(/^Health \d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Confidence \d/)).not.toBeInTheDocument();
  });

  it.each([undefined, { is_assessed: true, reason: "Assessment available.", source_ids: ["P-001"] }])("keeps numeric badges unless explicitly marked unassessed: %j", assessment => {
    state.assessment = assessment;
    renderNavigation("/projects/P-001?tab=overview");
    expect(screen.getByText("Health 0.0")).toBeInTheDocument();
    expect(screen.getByText("Confidence 0.0")).toBeInTheDocument();
    expect(screen.queryByText("Not yet assessed")).not.toBeInTheDocument();
    expect(screen.getByText("About health")).toBeInTheDocument();
    expect(screen.getByText("About data confidence")).toBeInTheDocument();
  });

  it.each([["gates", "About gate readiness"], ["requirements", "About trace state"], ["assumptions", "About assumption"]])("offers contextual help for %s", (tab, label) => {
    renderNavigation(`/projects/P-001?tab=${tab}`);
    expect(screen.getByText(label).tagName).toBe("SUMMARY");
  });
});