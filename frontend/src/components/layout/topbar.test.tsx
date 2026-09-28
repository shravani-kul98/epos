import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "@/components/layout/topbar";
import { renderWithProviders, tokenResponse } from "@/test-utils";

describe("TopBar attention summary", () => {
  it("names searchable records while preserving the workspace search action and shortcut hint", async () => {
    const open = vi.fn();
    renderWithProviders(<TopBar alerts={[]} onOpenCommandMenu={open} onOpenMobileNav={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Search workspace" });
    expect(trigger).toHaveTextContent("Search projects, tasks, risks");
    expect(trigger).toHaveTextContent("Ctrl K");
    await userEvent.setup().click(trigger);
    expect(open).toHaveBeenCalledTimes(1);
  });

  it("does not turn an unavailable portfolio response into zero alerts", async () => {
    renderWithProviders(<TopBar alerts={[]} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Alerts, summary unavailable" }));
    expect(screen.getByRole("status")).toHaveTextContent("No alert count is inferred.");
    expect(screen.queryByText(/No critical or high-severity alerts/)).not.toBeInTheDocument();
  });

  it("names a loading summary as loading rather than unavailable", async () => {
    renderWithProviders(<TopBar alerts={[]} alertsLoading onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Alerts, loading" }));
    expect(screen.getByRole("status")).toHaveTextContent("The portfolio summary is still loading.");
  });

  it("shows an empty state only when the API supplies a zero count", async () => {
    renderWithProviders(<TopBar alerts={[]} alertCount={0} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Alerts, 0 critical or high" }));
    expect(screen.getByText("No critical or high-severity alerts across the projects you can see.")).toBeInTheDocument();
  });

  it("keeps the API total when preview records are unavailable", async () => {
    renderWithProviders(<TopBar alerts={[]} alertCount={8} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);
    const user = userEvent.setup();

    const trigger = screen.getByRole("button", { name: "Alerts, 8 critical or high" });
    await user.click(trigger);
    expect(screen.getByText("Critical and high alerts · 8 total")).toBeInTheDocument();
    expect(screen.getByText(/no preview records are available/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole("region", { name: "Alerts" })).not.toBeInTheDocument();
  });

  it("connects the trigger to its panel and closes on an outside touch", async () => {
    renderWithProviders(<TopBar alerts={[]} alertCount={0} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Alerts, 0 critical or high" });
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-controls", screen.getByRole("region", { name: "Alerts" }).id);
    fireEvent.pointerDown(document.body, { pointerType: "touch" });
    expect(screen.queryByRole("region", { name: "Alerts" })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).not.toHaveAttribute("aria-controls");
  });

  it("does not expose the tactile create action without permission", () => {
    renderWithProviders(<TopBar alerts={[]} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);
    expect(screen.queryByRole("button", { name: "Create project" })).not.toBeInTheDocument();
  });
});

describe("TopBar inbox link", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("links to the inbox and names the unread count", async () => {
    window.localStorage.setItem("epos.access_token", "test-token");
    vi.stubGlobal("fetch", vi.fn(async (input: string) => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify(input.includes("/auth/me") ? JSON.parse(tokenResponse()).user : input.includes("/notifications/summary") ? { unread: 3 } : {}),
    })));
    renderWithProviders(<TopBar alerts={[]} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);

    expect(await screen.findByRole("link", { name: "Inbox, 3 unread" })).toHaveAttribute("href", "/inbox");
  });

  it("does not ask for the unread count before sign-in", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<TopBar alerts={[]} onOpenCommandMenu={() => {}} onOpenMobileNav={() => {}} />);

    expect(screen.getByRole("link", { name: "Inbox" })).toHaveAttribute("href", "/inbox");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});