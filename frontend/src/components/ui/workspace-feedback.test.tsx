import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilterBar } from "@/components/ui/filter-bar";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingRegion, Skeleton, SkeletonCards, SkeletonTable } from "@/components/ui/loading-skeleton";
import { PageContext, PageHeader } from "@/components/ui/page-header";
import { ApiError } from "@/lib/api";

afterEach(() => { vi.restoreAllMocks(); });

describe("Workspace feedback", () => {
  it("names active filters, preserves clear actions and announces a copied view", async () => {
    const clear = vi.fn();
    const user = userEvent.setup();
    const copy = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<FilterBar active onClear={clear}><label>Owner<input /></label></FilterBar>);
    expect(screen.getByText("Filters applied")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Share view" }));
    expect(copy).toHaveBeenCalledWith(window.location.href);
    expect(screen.getByRole("status")).toHaveTextContent("View link copied.");
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(clear).toHaveBeenCalledOnce();
  });

  it("offers a safe fallback when clipboard access is blocked", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("not available"));
    render(<FilterBar><span>Scope</span></FilterBar>);
    await user.click(screen.getByRole("button", { name: "Share view" }));
    expect(screen.getByRole("status")).toHaveTextContent("Copy the browser address");
    expect(screen.queryByText("View link copied.")).not.toBeInTheDocument();
    expect(screen.queryByText("Filters applied")).not.toBeInTheDocument();
  });

  it("retains retry semantics and does not expose unexpected exception details", () => {
    const retry = vi.fn();
    const { rerender } = render(<ErrorState error={new Error("internal trace must not render")} onRetry={retry} />);
    expect(screen.getByRole("alert")).not.toHaveTextContent("internal trace");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    rerender(<ErrorState error={new ApiError(403, "Not permitted")} onRetry={retry} />);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("keeps skeletons decorative and announces one supplied loading message", () => {
    const { container } = render(<><LoadingRegion label="Loading project records" /><SkeletonCards count={2} /><SkeletonTable rows={3} /><Skeleton aria-hidden="true" data-testid="native-skeleton" /></>);
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading project records");
    expect(screen.getByTestId("native-skeleton")).toHaveAttribute("data-slot", "skeleton");
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(16);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows the actual analysis date rather than implying live data", () => {
    render(<PageContext.Provider value={{ scope: "Selected portfolio", asOfDate: "2026-08-25" }}><PageHeader title="Executive summary" /></PageContext.Provider>);
    expect(screen.getByRole("heading", { level: 1, name: "Executive summary" })).toBeInTheDocument();
    expect(screen.getByText("Selected portfolio")).toBeInTheDocument();
    expect(screen.getByText("25 Aug 2026")).toHaveAttribute("datetime", "2026-08-25");
  });
});
