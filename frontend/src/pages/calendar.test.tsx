import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalendarPage } from "@/pages/calendar";
import { renderWithProviders, tokenResponse } from "@/test-utils";

afterEach(()=>{vi.unstubAllGlobals();window.localStorage.clear();});
const ok=(body:unknown)=>({ok:true,status:200,text:async()=>JSON.stringify(body)});

describe("Calendar date semantics",()=>{
  it("starts from the API analysis date and labels raised dates honestly",async()=>{
    window.localStorage.setItem("epos.access_token","test-token");
    vi.stubGlobal("fetch",vi.fn(async (input:string)=>{
      if(input.includes("/auth/me"))return ok(JSON.parse(tokenResponse()).user);
      if(input.includes("/analytics/portfolio"))return ok({as_of_date:"2026-08-25",projects:[]});
      if(input.includes("/change-requests"))return ok([{change_request_id:"CR-TEST",project_id:"P-TEST",requested_date:"2026-08-12",change_description:"Recorded scope change"}]);
      return ok([]);
    }));
    renderWithProviders(<CalendarPage/>);
    expect(await screen.findByRole("heading",{name:"Agenda · August 2026"})).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"Recorded scope change"})).toHaveAttribute("href","/projects/P-TEST?tab=changes");
    expect(screen.getByRole("button",{name:"Change raised"})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Change review"})).not.toBeInTheDocument();
  });
});