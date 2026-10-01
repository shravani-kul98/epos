import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingPage } from "@/pages/onboarding";

const auth = vi.hoisted(() => ({ role: "engineer", roleLabel: "Engineer", permissions: [] as string[] }));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { full_name: "Synthetic Reviewer", role: auth.role, role_label: auth.roleLabel },
    can: (permission: string) => auth.permissions.includes(permission),
  }),
}));

function Destination(): JSX.Element {
  return <output aria-label="Destination">{useLocation().pathname}</output>;
}

function renderOnboarding(): void {
  render(<MemoryRouter initialEntries={["/welcome"]}><OnboardingPage /><Destination /></MemoryRouter>);
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    auth.role = "engineer";
    auth.roleLabel = "Engineer";
    auth.permissions = [];
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("offers the engineer's next step immediately without a preference questionnaire", async () => {
    renderOnboarding();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Start with your work" })).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText(/ask your project manager to add you to the team/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create a project" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "View my work" }));
    expect(screen.getByLabelText("Destination")).toHaveTextContent("/my-work");
    expect(window.localStorage.getItem("epos.focus")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("teaches health, data confidence and analysis date on the same screen", () => {
    renderOnboarding();
    const guide = screen.getByRole("region", { name: "Read the signals separately" });
    expect(within(guide).getByText("Health")).toBeInTheDocument();
    expect(within(guide).getByText(/How the recorded work compares/)).toHaveTextContent("No colour guarantees delivery or sets a response deadline");
    expect(within(guide).getByText("Data confidence")).toBeInTheDocument();
    expect(within(guide).getByText(/How recently records were updated/)).toHaveTextContent("not a probability of success or a guarantee that the data is correct");
    expect(within(guide).getByText("Analysis date")).toBeInTheDocument();
    expect(within(guide).getByText(/Defaults to today in UTC/)).toHaveTextContent("does not restore a historical snapshot");
  });

  it.each([
    ["engineering_lead", "Engineering Lead", "portfolio.read", "Review project delivery", "/projects"],
    ["project_manager", "Project Manager", "portfolio.read", "Open your projects", "/projects"],
    ["requirements_manager", "Requirements Manager", "portfolio.read", "Review requirements", "/requirements"],
    ["pmo_analyst", "PMO Analyst", "portfolio.read", "Review the portfolio", "/portfolio"],
    ["executive", "Executive", "portfolio.read", "Review the portfolio", "/portfolio"],
    ["administrator", "Administrator", "user.manage", "Review team access", "/admin/users"],
  ])("provides a role-focused next step for %s", async (role, label, permission, action, path) => {
    auth.role = role;
    auth.roleLabel = label;
    auth.permissions = [permission];
    renderOnboarding();
    expect(screen.getByText(label)).toBeInTheDocument();
    await userEvent.setup().click(within(screen.getByRole("region", { name: "Your next step" })).getByRole("button", { name: action }));
    expect(screen.getByLabelText("Destination")).toHaveTextContent(path);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not infer permissions from an administrator role label", async () => {
    auth.role = "administrator";
    auth.roleLabel = "Administrator";
    renderOnboarding();
    expect(screen.queryByRole("button", { name: "Review team access" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create a project" })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "View my work" }));
    expect(screen.getByLabelText("Destination")).toHaveTextContent("/my-work");
  });

  it("only offers project creation with its permission", async () => {
    auth.permissions = ["project.create"];
    renderOnboarding();
    await userEvent.setup().click(screen.getByRole("button", { name: "Create a project" }));
    expect(screen.getByLabelText("Destination")).toHaveTextContent("/projects/new");
  });

  it.each([["Go to home", "/"], ["Role and permissions", "/account/role"]])("allows direct navigation through %s", async (action, path) => {
    renderOnboarding();
    await userEvent.setup().click(screen.getByRole("button", { name: action }));
    expect(screen.getByLabelText("Destination").textContent).toBe(path);
  });
});