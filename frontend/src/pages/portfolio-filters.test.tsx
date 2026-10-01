import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PortfolioPage } from "@/pages/portfolio";
import { renderWithProviders, tokenResponse } from "@/test-utils";

const projects=[
  {project_id:"P-TEST-A",project_name:"Recorded Alpha",project_manager:"Synthetic Owner",project_phase:"Execution",domain:"Engineering",business_priority:"High",forecast_end_date:"2026-10-01",health_score:59.25,health_band:"Red",confidence_score:82,confidence_band:"High",open_alert_count:1,critical_alert_count:1},
  {project_id:"P-TEST-B",project_name:"Recorded Beta",project_manager:"Synthetic Owner",project_phase:"Execution",domain:"Engineering",business_priority:"High",forecast_end_date:"2026-10-15",health_score:85,health_band:"Green",confidence_score:82,confidence_band:"High",open_alert_count:0,critical_alert_count:0},
];
const base={as_of_date:"2026-08-25",project_count:2,health_bands:{red:1,amber:0,green:1},confidence_bands:{high:2,medium:0,low:0},alert_severities:{critical:1,high:0,medium:0,low:0},project_phases:{Execution:2},project_domains:{Engineering:2},projects,top_alerts:[]};
function Probe(){return <output data-testid="url">{useLocation().search}</output>;}
const ok=(body:unknown)=>({ok:true,status:200,text:async()=>JSON.stringify(body)});

afterEach(()=>{vi.unstubAllGlobals();window.localStorage.clear();});

function setup(route="/portfolio") {
  window.localStorage.setItem("epos.access_token","test-token");
  const fetchMock=vi.fn(async (input:string)=>{
    const url=new URL(input,"http://localhost");
    if(url.pathname.endsWith("/auth/me")) return ok(JSON.parse(tokenResponse()).user);
    if(url.searchParams.get("health_band")==="Red") return ok({...base,project_count:1,health_bands:{red:1,amber:0,green:0},confidence_bands:{high:1,medium:0,low:0},projects:[projects[0]],project_phases:{Execution:1},project_domains:{Engineering:1}});
    return ok(base);
  });
  vi.stubGlobal("fetch",fetchMock);
  renderWithProviders(<><PortfolioPage/><Probe/></>,{route});
  return fetchMock;
}

describe("Portfolio shared views",()=>{
  it("restores URL filters and renders the API's scoped values without score changes",async()=>{
    setup("/portfolio?health_band=Red");
    const table=within(await screen.findByRole("region",{name:"Portfolio projects table"}));
    expect(table.getByText("Recorded Alpha")).toBeInTheDocument();
    expect(table.queryByText("Recorded Beta")).not.toBeInTheDocument();
    expect(table.getByText("59.3")).toBeInTheDocument();
    expect(screen.getByLabelText("Health band")).toHaveValue("Red");
  });

  it("cross-filters from a chart and can restore the whole authorized view",async()=>{
    setup();
    const user=userEvent.setup();
    await user.click(await screen.findByRole("button",{name:"Filter by Red"}));
    await waitFor(()=>expect(screen.getByTestId("url")).toHaveTextContent("health_band=Red"));
    await waitFor(()=>expect(within(screen.getByRole("region",{name:"Portfolio projects table"})).queryByText("Recorded Beta")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button",{name:"Clear filters"}));
    expect(await within(await screen.findByRole("region",{name:"Portfolio projects table"})).findByText("Recorded Beta")).toBeInTheDocument();
  });
});