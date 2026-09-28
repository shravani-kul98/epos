import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { RequirementRegister } from "@/components/requirement-register";
import { renderWithProviders } from "@/test-utils";
import type { TraceabilityRow } from "@/types/api";

const row: TraceabilityRow={requirement_id:"REQ-TEST",requirement_text:"Recorded verification requirement",project_id:"P-TEST",requirement_status:"Approved",priority:"High",owner:null,linked_test_case_ids:["TC-TEST"],verified_test_case_ids:[],trace_status:"Not verified",open_change_request_ids:[]};

describe("Requirement register",()=>{
  it("keeps an unverified link distinct from verified evidence",async()=>{
    renderWithProviders(<RequirementRegister rows={[row]} isLoading={false} onRetry={()=>{}}/>);
    const user=userEvent.setup();
    await user.click(screen.getByRole("button",{name:"Open REQ-TEST"}));
    const dialog=within(screen.getByRole("dialog"));
    expect(dialog.getByText("Not verified")).toHaveClass("text-critical");
    expect(dialog.getByText("Linked; verification not established")).toBeInTheDocument();
    expect(dialog.queryByText("Verified evidence recorded")).not.toBeInTheDocument();
    expect(dialog.getByRole("button",{name:"Inspect source TC-TEST"})).toBeInTheDocument();
  });
  it("offers a hierarchy made from actual project and test links",async()=>{
    renderWithProviders(<RequirementRegister rows={[row]} isLoading={false} onRetry={()=>{}}/>);
    await userEvent.setup().click(screen.getByRole("button",{name:"Requirements explorer"}));
    expect(screen.getByText("Project P-TEST · requirements and recorded test links")).toBeInTheDocument();
    expect(screen.getByText("TC-TEST")).toBeInTheDocument();
  });
});