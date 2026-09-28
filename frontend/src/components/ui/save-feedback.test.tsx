import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SaveFeedback } from "@/components/ui/save-feedback";
import { request } from "@/lib/api";
import { announceSaved, saveFeedback } from "@/lib/save-feedback";

afterEach(() => { saveFeedback.clear(); vi.unstubAllGlobals(); });

describe("Visible save feedback", () => {
  it("announces successful saves and lets keyboard users dismiss them", async () => {
    render(<SaveFeedback />);
    act(() => announceSaved("POST", "/tasks/T-EXAMPLE/complete"));
    expect(screen.getByRole("status")).toHaveTextContent("Task completion recorded");
    const user = userEvent.setup();
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("never calls a failed save successful", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409, text: async () => JSON.stringify({ detail: "Stale record" }) })));
    render(<SaveFeedback />);
    await expect(request("/tasks/T-EXAMPLE", { method: "PATCH", body: { row_version: 1 } })).rejects.toThrow("Stale record");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("does not announce read-only analysis or AI as a data change", () => {
    render(<SaveFeedback />);
    act(() => { announceSaved("GET", "/tasks"); announceSaved("POST", "/copilot/ask"); announceSaved("POST", "/scenarios/dependency-delay"); });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
