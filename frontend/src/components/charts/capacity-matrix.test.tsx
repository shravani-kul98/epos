import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CapacityMatrix } from "@/components/charts/capacity-matrix";

describe("Capacity matrix",()=>{
  it("renders recorded utilisation and over-capacity without relying on colour",()=>{
    render(<CapacityMatrix records={[{resource_id:"RES-TEST",resource_name:"Synthetic Engineer",project_id:"P-TEST",allocated_hours:60,capacity_hours:40,utilisation_percent:150,is_overallocated:true,week_start_date:"2026-08-24"}]}/>);
    expect(screen.getByText("150%")).toBeInTheDocument();
    expect(screen.getByText("60 / 40 hours")).toBeInTheDocument();
    expect(screen.getByText("Over capacity")).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAccessibleName("Resource utilisation from weekly allocation records");
  });
});