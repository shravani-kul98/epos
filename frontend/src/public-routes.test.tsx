import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "@/App";
import { renderWithProviders, tokenResponse } from "@/test-utils";

vi.mock("@/pages/home", () => ({ HomePage: () => <h1>Executive summary</h1> }));
afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Welcome route boundaries", () => {
  it("renders the public root rather than redirecting it to login", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<App />, { route: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: /Complex projects/ })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each(["/", "/login", "/register"])("does not display a creator credit on %s", async (route) => {
    vi.stubGlobal("fetch", vi.fn());
    renderWithProviders(<App />, { route });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("button", { name: "About this interface" })).not.toBeInTheDocument();
    expect(screen.queryByText(/made by/i)).not.toBeInTheDocument();
  });
  it("keeps the signed-in root in the protected dashboard", async () => {
    window.localStorage.setItem("epos.access_token", "test-token");
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ({ ok: true, status: 200, text: async () => JSON.stringify(
      input.includes("/auth/me") ? JSON.parse(tokenResponse()).user : { as_of_date: "2026-08-25", projects: [], top_alerts: [], alert_severities: { critical: 0, high: 0, medium: 0, low: 0 } },
    ) })));
    renderWithProviders(<App />, { route: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: "Executive summary" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About this interface" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Complex projects/ })).not.toBeInTheDocument();
  });
  it("still requires authentication for protected deep links", async () => {
    const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<App />, { route: "/projects/P-001?tab=work" });
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Product capabilities" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});