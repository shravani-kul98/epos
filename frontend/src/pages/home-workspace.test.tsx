import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "@/pages/home";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const EMPTY_PORTFOLIO = {
  as_of_date: "2026-08-25", project_count: 0,
  health_bands: { red: 0, amber: 0, green: 0 }, confidence_bands: { low: 0, medium: 0, high: 0 },
  alert_severities: { critical: 0, high: 0, medium: 0, low: 0 }, projects: [], top_alerts: [],
};
const ok = (body: unknown) => ({ ok: true, status: 200, text: async () => JSON.stringify(body) });

beforeEach(() => { window.localStorage.setItem("epos.access_token", "test-token"); });
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Executive workspace", () => {
  it("keeps shortcuts permission-aware and navigation free of nested buttons", async () => {
    const profile = JSON.parse(tokenResponse({ permissions: ["portfolio.read"] })).user;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/auth/me")) return ok(profile);
      if (String(url).includes("/analytics/portfolio")) return ok(EMPTY_PORTFOLIO);
      return ok([]);
    }));
    const { container } = renderWithProviders(<HomePage />);
    await screen.findByRole("heading", { name: "No projects yet" });
    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
    const shortcuts = within(screen.getByRole("navigation", { name: "Workspace shortcuts" }));
    expect(shortcuts.getByRole("link", { name: "My work" })).toHaveAttribute("href", "/my-work");
    expect(shortcuts.getByRole("link", { name: "Calendar" })).toHaveAttribute("href", "/calendar");
    expect(shortcuts.queryByRole("link", { name: "Explore a scenario" })).not.toBeInTheDocument();
    expect(shortcuts.queryByRole("link", { name: "Executive report" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ask EPOS" })).not.toBeInTheDocument();
    expect(container.querySelector("a button, button a")).not.toBeInTheDocument();
  });

  it("lists the projects the API flags for attention, including amber ones, and links to that view", async () => {
    const profile = JSON.parse(tokenResponse({ permissions: ["portfolio.read"] })).user;
    const project = (id: string, name: string, band: string, score: number, flagged: boolean) => ({
      project_id: id, project_name: name, domain: "Engineering", project_manager: "Synthetic Owner", project_phase: "Execution",
      business_priority: "High", forecast_end_date: "2026-10-01", health_score: score, health_band: band, confidence_score: 80,
      confidence_band: "High", open_alert_count: 1, critical_alert_count: 0, needs_attention: flagged,
      assessment: { is_assessed: true, reason: "", source_ids: [] },
    });
    const portfolio = {
      ...EMPTY_PORTFOLIO, project_count: 2, health_bands: { red: 0, amber: 1, green: 1 },
      projects: [project("P-AMBER", "Watched Amber programme", "Amber", 62.5, true), project("P-GREEN", "Steady Green programme", "Green", 88, false)],
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/auth/me")) return ok(profile);
      if (String(url).includes("/analytics/portfolio")) return ok(portfolio);
      return ok([]);
    }));
    renderWithProviders(<HomePage />);
    const amber = await screen.findByRole("link", { name: /Watched Amber programme/ });
    expect(amber).toHaveAttribute("href", "/projects/P-AMBER");
    expect(screen.queryByRole("link", { name: /Steady Green programme/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Needing attention/ })).toHaveAttribute("href", "/portfolio?needs_attention=true");
  });

  it("marks refresh as pending without replacing the last supplied metrics", async () => {
    const profile = JSON.parse(tokenResponse()).user;
    let portfolioRequests = 0;
    let finish: (value: ReturnType<typeof ok>) => void = () => {};
    const pending = new Promise<ReturnType<typeof ok>>(resolve => { finish = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/auth/me")) return ok(profile);
      if (String(url).includes("/analytics/portfolio")) return ++portfolioRequests === 1 ? ok(EMPTY_PORTFOLIO) : pending;
      return ok([]);
    }));
    renderWithProviders(<HomePage />);
    await screen.findByRole("heading", { name: "No projects yet" });
    expect(screen.getByRole("link", { name: "Create project" })).toHaveAttribute("href", "/projects/new");
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));
    const button = screen.getByRole("button", { name: "Refreshing" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("progressbar", { name: "Refreshing portfolio summary" })).not.toHaveAttribute("aria-valuenow");
    expect(screen.getByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    await userEvent.click(button);
    expect(portfolioRequests).toBe(2);
    finish(ok(EMPTY_PORTFOLIO));
    expect(await screen.findByRole("button", { name: "Refresh" })).toBeEnabled();
  });
});
