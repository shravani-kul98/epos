import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getCsrfToken, hasSessionHint, request, SESSION_HINT_KEY, setCsrfToken, setSessionHint } from "@/lib/api";

afterEach(()=>{vi.unstubAllGlobals();setCsrfToken(null);window.localStorage.clear();});

function header(init: RequestInit | undefined, name: string): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.[name];
}

function recordingFetch(status = 200) {
  return vi.fn(async (url: string, init?: RequestInit) => ({
    ok: true,
    status,
    text: async () => (status === 204 ? "" : JSON.stringify({ url, method: init?.method ?? "GET" })),
  }));
}

describe("Cookie session requests", () => {
  it("identifies the web client on every request and echoes the CSRF token only on writes", async () => {
    window.localStorage.setItem(SESSION_HINT_KEY, "legacy-bearer-value");
    const fetchMock = recordingFetch();
    vi.stubGlobal("fetch", fetchMock);
    setCsrfToken("csrf-synthetic");

    await request("/projects");
    await request("/projects", { method: "POST", body: { project_name: "Synthetic" } });

    const [read, write] = fetchMock.mock.calls;
    expect(read?.[1]?.credentials).toBe("same-origin");
    expect(header(read?.[1], "X-EPOS-Client")).toBe("web");
    expect(header(read?.[1], "X-CSRF-Token")).toBeUndefined();
    expect(header(read?.[1], "Authorization")).toBeUndefined();
    expect(write?.[1]?.credentials).toBe("same-origin");
    expect(header(write?.[1], "X-EPOS-Client")).toBe("web");
    expect(header(write?.[1], "X-CSRF-Token")).toBe("csrf-synthetic");
    expect(header(write?.[1], "Authorization")).toBeUndefined();
  });

  it("sends no CSRF header before a session supplied one", async () => {
    const fetchMock = recordingFetch(204);
    vi.stubGlobal("fetch", fetchMock);

    await request("/auth/logout", { method: "POST" });

    expect(getCsrfToken()).toBeNull();
    expect(header(fetchMock.mock.calls[0]?.[1], "X-CSRF-Token")).toBeUndefined();
    expect(header(fetchMock.mock.calls[0]?.[1], "X-EPOS-Client")).toBe("web");
  });

  it("stores only a marker as the session hint", () => {
    setSessionHint(true);
    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBe("cookie");
    expect(hasSessionHint()).toBe(true);
    setSessionHint(false);
    expect(window.localStorage.getItem(SESSION_HINT_KEY)).toBeNull();
    expect(hasSessionHint()).toBe(false);
  });
});

describe("API error presentation",()=>{
  it.each([403,404,500])("never exposes sensitive server detail for status %s",async status=>{
    vi.stubGlobal("fetch",vi.fn(async()=>({ok:false,status,text:async()=>JSON.stringify({detail:"Private internal record and stack trace"})})));
    await expect(request("/test")).rejects.not.toThrow("Private internal record");
  });
  it("maps validation messages without copying submitted input",async()=>{
    vi.stubGlobal("fetch",vi.fn(async()=>({ok:false,status:422,text:async()=>JSON.stringify({detail:[{loc:["body","title"],msg:"Title is required",input:"never display submitted data"}]})})));
    try { await request("/test"); throw new Error("Expected a validation failure"); } catch(error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).fieldErrors).toEqual({title:"Title is required"});
      expect((error as Error).message).not.toContain("never display");
    }
  });
});