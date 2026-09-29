import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RiskHeatmap } from "@/components/charts/risk-heatmap";
import type { Risk } from "@/types/api";

const risk: Risk = { risk_id:"R-TEST", project_id:"P-TEST", risk_name:"Recorded risk", probability:4, impact:5, severity_score:20, status:"Open", mitigation_owner:null, mitigation_status:null, due_date:"2026-09-15" };

describe("RiskHeatmap", () => {
  it("announces coordinates and counts and selects the exact cell by keyboard", async () => {
    const select=vi.fn();
    render(<MemoryRouter><RiskHeatmap risks={[risk]} onSelectCell={select} selectedCell={[4,5]} /></MemoryRouter>);
    const cell=screen.getByRole("button", {name:"Probability 4, impact 5: 1 risk"});
    expect(cell).toHaveAttribute("aria-pressed","true");
    cell.focus();
    await userEvent.setup().keyboard("{Enter}");
    expect(select).toHaveBeenCalledWith(4,5);
    expect(screen.getByRole("button", {name:"Probability 1, impact 1: 0 risks"})).toBeDisabled();
    expect(screen.getByRole("table",{name:"Risk matrix records"})).toHaveTextContent("R-TEST");
  });

  it("does not round or invent recorded coordinates", () => {
    render(<MemoryRouter><RiskHeatmap risks={[]} /></MemoryRouter>);
    expect(screen.getAllByRole("button")).toHaveLength(25);
    expect(screen.getAllByRole("button").every(button=>button.hasAttribute("disabled"))).toBe(true);
  });
});