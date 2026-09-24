import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUpdateRisk } from "@/lib/queries";
import { createTestQueryClient } from "@/test-utils";

afterEach(()=>{vi.unstubAllGlobals();});
describe("Read-model coordination",()=>{
  it("invalidates global/scoped registers, portfolio filters and reports after a risk edit",async()=>{
    vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,status:200,text:async()=>JSON.stringify({risk_id:"R-TEST",project_id:"P-TEST"})})));
    const client=createTestQueryClient();
    const keys=[["risk-register","all"],["risk-register","P-TEST"],["portfolio"],["portfolio","view",{health_band:"Red"}],["executive-report",7],["risks","P-TEST"]];
    for(const key of keys) client.setQueryData(key,[]);
    const wrapper=({children}:{children:ReactNode})=><QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const {result}=renderHook(()=>useUpdateRisk("P-TEST"),{wrapper});
    await act(async()=>{await result.current.mutateAsync({riskId:"R-TEST",patch:{row_version:1,mitigation_owner:"Synthetic Owner"}});});
    for(const key of keys) expect(client.getQueryState(key)?.isInvalidated,JSON.stringify(key)).toBe(true);
    client.clear();
  });
});