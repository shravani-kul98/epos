import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Home } from "lucide-react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandMenu } from "@/components/ui/command-menu";
import { renderWithProviders } from "@/test-utils";
import type { NavigationItem } from "@/components/layout/navigation";
import type { ProjectSummary } from "@/types/api";

const NAVIGATION = [
  { label: "Home", path: "/", icon: Home, section: "Overview" },
  { label: "Decisions", path: "/decisions", icon: Home, section: "Control" },
] as unknown as NavigationItem[];

const PROJECTS = [
  {
    project_id: "P-002",
    project_name: "Supplier Data Migration",
    health_band: "Red",
  },
] as unknown as ProjectSummary[];

function hit(overrides: Record<string, unknown> = {}): unknown {
  return {
    record_type: "risk",
    record_type_label: "Risk",
    record_id: "R-2001",
    title: "Supplier data quality is incomplete",
    subtitle: "Alex Morgan",
    status: "Open",
    project_id: "P-002",
    project_name: "Supplier Data Migration",
    path: "/projects/P-002?tab=risks",
    ...overrides,
  };
}

function mockSearch(body: Record<string, unknown>) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workspace search", () => {
  it("has a named dialog and closes with Escape", async () => {
    const close = vi.fn();
    renderWithProviders(<CommandMenu open onClose={close} navigation={NAVIGATION} projects={PROJECTS}/>);
    expect(screen.getByRole("dialog",{name:"Search workspace"})).toBeInTheDocument();
    await userEvent.setup().keyboard("{Escape}");
    expect(close).toHaveBeenCalledTimes(1);
  });
  it("finds records that are not pages or projects", async () => {
    vi.stubGlobal("fetch", mockSearch({ query: "supplier", total: 1, hits: [hit()] }));
    renderWithProviders(
      <CommandMenu open onClose={() => {}} navigation={NAVIGATION} projects={PROJECTS} />,
    );

    await userEvent.type(screen.getByLabelText("Search the workspace"), "supplier");

    expect(
      await screen.findByText("Supplier data quality is incomplete", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Risk")).toBeInTheDocument();
  });

  it("does not call the API until the query is worth searching", async () => {
    const fetchMock = mockSearch({ query: "s", total: 0, hits: [] });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(
      <CommandMenu open onClose={() => {}} navigation={NAVIGATION} projects={PROJECTS} />,
    );

    await userEvent.type(screen.getByLabelText("Search the workspace"), "s");

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says how many further records also matched", async () => {
    vi.stubGlobal("fetch", mockSearch({ query: "supplier", total: 34, hits: [hit()] }));
    renderWithProviders(
      <CommandMenu open onClose={() => {}} navigation={NAVIGATION} projects={PROJECTS} />,
    );

    await userEvent.type(screen.getByLabelText("Search the workspace"), "supplier");

    await waitFor(() =>
      expect(screen.getByText(/33 more records also match/)).toBeInTheDocument(),
    );
  });

  it("still resolves pages and projects without waiting for the API", async () => {
    vi.stubGlobal("fetch", mockSearch({ query: "decisions", total: 0, hits: [] }));
    renderWithProviders(
      <CommandMenu open onClose={() => {}} navigation={NAVIGATION} projects={PROJECTS} />,
    );

    await userEvent.type(screen.getByLabelText("Search the workspace"), "decision");

    expect(screen.getByRole("button", { name: /Decisions/ })).toBeInTheDocument();
  });

  it("closes when a result is chosen", async () => {
    const onClose = vi.fn();
    vi.stubGlobal("fetch", mockSearch({ query: "supplier", total: 1, hits: [hit()] }));
    renderWithProviders(
      <CommandMenu open onClose={onClose} navigation={NAVIGATION} projects={PROJECTS} />,
    );

    await userEvent.type(screen.getByLabelText("Search the workspace"), "supplier");
    await userEvent.click(await screen.findByText("Supplier data quality is incomplete"));

    expect(onClose).toHaveBeenCalled();
  });

  it("exposes a named close control for touch users", async () => {
    const close = vi.fn();
    renderWithProviders(<CommandMenu open onClose={close} navigation={NAVIGATION} projects={PROJECTS} />);
    await userEvent.click(screen.getByRole("button", { name: "Close workspace search" }));
    expect(close).toHaveBeenCalledOnce();
  });

  it("keeps keyboard selection and ignores Enter during input composition", async () => {
    const close = vi.fn();
    renderWithProviders(<CommandMenu open onClose={close} navigation={NAVIGATION} projects={PROJECTS} />);
    const search = screen.getByRole("textbox", { name: "Search the workspace" });
    fireEvent.keyDown(search, { key: "Enter", isComposing: true });
    expect(close).not.toHaveBeenCalled();
    search.focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: "Decisions" })).toHaveAttribute("data-active", "true");
    await userEvent.keyboard("{Enter}");
    expect(close).toHaveBeenCalledOnce();
  });
});
