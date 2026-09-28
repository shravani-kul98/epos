import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GatePosition } from "@/components/gate-position";
import { renderWithProviders } from "@/test-utils";
import type { Gate } from "@/types/api";

afterEach(()=>{vi.unstubAllGlobals();});
const gate: Gate={gate_id:"G-TEST",project_id:"P-TEST",milestone_id:null,gate_name:"Recorded release gate",sequence:1,planned_review_date:"2026-09-01",actual_review_date:null,owner:"Synthetic Owner",status:"Preparing",review_cycle:1,result:null,applicable_baseline:null};

describe("Gate readiness position",()=>{
  it("keeps mandatory blockers ahead of a supplied completion percentage",async()=>{
    vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,status:200,text:async()=>JSON.stringify({state:"Not Ready",percentage:100,blockers:[{message:"Mandatory approval remains unresolved",source_ids:["G-TEST"]}],warnings:[],latest_review_outcome:null})})));
    renderWithProviders(<GatePosition gate={gate}/>);
    const blocker=await screen.findByText("Mandatory blockers remain");
    const percentage=screen.getByText(/100% of assessed criteria complete/);
    expect(blocker.compareDocumentPosition(percentage)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText("Not Ready")).toBeInTheDocument();
    expect(screen.getByText("Human review: Not recorded")).toBeInTheDocument();
  });
});