import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "@/App";
import { renderWithProviders, tokenResponse } from "@/test-utils";

afterEach(()=>{window.localStorage.clear();vi.unstubAllGlobals();});
const ok=(body:unknown)=>({ok:true,status:200,text:async()=>JSON.stringify(body)});

describe("Application route boundaries",()=>{
  it("redirects an anonymous visitor before protected data is requested",async()=>{
    const fetchMock=vi.fn();vi.stubGlobal("fetch",fetchMock);
    renderWithProviders(<App/>,{route:"/scenarios"});
    expect(await screen.findByRole("heading",{name:"Sign in"})).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("does not load a restricted scenario page or expose its records",async()=>{
    window.localStorage.setItem("epos.access_token","test-token");
    const fetchMock=vi.fn(async (input:string)=> input.includes("/auth/me") ? ok(JSON.parse(tokenResponse({permissions:["portfolio.read"]})).user) : ok({as_of_date:"2026-08-25",projects:[],top_alerts:[],alert_severities:{critical:0,high:0,medium:0,low:0}}));
    vi.stubGlobal("fetch",fetchMock);
    renderWithProviders(<App/>,{route:"/scenarios"});
    expect(await screen.findByRole("heading",{name:"Access restricted"})).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url])=>url.includes("/scenarios/"))).toBe(false);
    expect(screen.queryByRole("link",{name:"Scenarios"})).not.toBeInTheDocument();
  });
});