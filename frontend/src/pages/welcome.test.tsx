import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WelcomePage } from "@/pages/welcome";
import { renderWithProviders } from "@/test-utils";

function Location(): JSX.Element {
  return <output aria-label="Current route">{useLocation().pathname}</output>;
}

afterEach(() => { window.localStorage.clear(); vi.unstubAllGlobals(); });

describe("Public welcome page", () => {
  it("explains four capabilities without requesting private records", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<WelcomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Complex projects.");
    expect(screen.getByText("One explainable view over your engineering programme")).toBeInTheDocument();
    for (const name of ["Health Score", "Risk Intelligence", "Traceability", "AI Copilot"]) {
      expect(screen.getByRole("tab", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Interactive overview · no live project data")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#welcome-main");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([["Sign in", "/login"], ["Create account", "/register"]])("routes %s to the existing auth page", async (label, path) => {
    renderWithProviders(<><WelcomePage /><Location /></>);
    await userEvent.setup().click(screen.getByRole("button", { name: label }));
    expect(screen.getByLabelText("Current route")).toHaveTextContent(path);
  });

  it("lets the user stop the decorative background without disabling the page", async () => {
    const { container } = renderWithProviders(<WelcomePage />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Pause background animation" }));
    expect(container.querySelector("[data-motion-paused=true]")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="light-rays"]')).toHaveAttribute("data-paused", "true");
    await user.click(screen.getByRole("button", { name: "Resume background animation" }));
    expect(container.querySelector('[data-slot="light-rays"]')).toHaveAttribute("data-paused", "false");
  });

  it("explains the selected capability without accessing project data", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<WelcomePage />);
    const user = userEvent.setup();
    for (const tab of screen.getAllByRole("tab")) {
      expect(document.getElementById(tab.getAttribute("aria-controls")!)).toBeInTheDocument();
    }
    await user.click(screen.getByRole("tab", { name: "Traceability" }));
    const panel = screen.getByRole("tabpanel", { name: "Traceability" });
    expect(within(panel).getByRole("heading")).toHaveTextContent("See how the work connects.");
    expect(within(panel).getByText("Requirements")).toBeInTheDocument();
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    await user.click(screen.getByRole("tab", { name: "AI Copilot" }));
    expect(screen.getByRole("tabpanel", { name: "AI Copilot" })).toHaveTextContent("When configured, AI explains selected evidence");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});